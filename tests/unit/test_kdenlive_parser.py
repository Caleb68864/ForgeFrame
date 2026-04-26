"""Unit tests for the Kdenlive XML parser."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.core.models.kdenlive import KdenliveProject

# ---------------------------------------------------------------------------
# Minimal XML helpers
# ---------------------------------------------------------------------------

_MINIMAL_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt title="Test Project" version="7.2">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1" colorspace="709"/>
      <producer id="prod0" in="0" out="99">
        <property name="resource">/tmp/clip.mp4</property>
        <property name="length">100</property>
      </producer>
      <playlist id="pl0">
        <entry producer="prod0" in="0" out="99"/>
      </playlist>
      <tractor id="tractor0" in="0" out="99">
        <track producer="pl0"/>
      </tractor>
      <unknown_custom_tag attr="value">some text</unknown_custom_tag>
    </mlt>
""")

_GUIDE_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt title="Guides Test" version="7">
      <profile width="1280" height="720" frame_rate_num="30" frame_rate_den="1"/>
      <guide position="75" comment="Chapter 1" type="chapter"/>
      <guide position="200" comment="Key moment"/>
    </mlt>
""")

_MALFORMED_INNER_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt title="Malformed" version="7">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1"/>
      <producer id="">
        <property name="resource">/clip.mp4</property>
      </producer>
    </mlt>
""")


def _write_temp(tmp_path: Path, content: str, filename: str = "test.kdenlive") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParserBasic:
    def test_returns_kdenlive_project(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert isinstance(project, KdenliveProject)

    def test_captures_version(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert project.version == "7.2"

    def test_captures_title(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert project.title == "Test Project"

    def test_profile_parsed(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert project.profile.width == 1920
        assert project.profile.height == 1080
        assert project.profile.fps == 25.0
        assert project.profile.colorspace == "709"

    def test_producers_parsed(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert len(project.producers) == 1
        p = project.producers[0]
        assert p.id == "prod0"
        assert p.resource == "/tmp/clip.mp4"
        assert p.properties["length"] == "100"

    def test_playlist_parsed(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert len(project.playlists) == 1
        pl = project.playlists[0]
        assert pl.id == "pl0"
        assert len(pl.entries) == 1
        entry = pl.entries[0]
        assert entry.producer_id == "prod0"
        assert entry.in_point == 0
        assert entry.out_point == 99

    def test_tracks_from_tractor(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        assert len(project.tracks) == 1
        assert project.tracks[0].id == "pl0"


class TestParserOpaqueElements:
    def test_unknown_element_stored_as_opaque(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        opaque_tags = [o.tag for o in project.opaque_elements]
        assert "unknown_custom_tag" in opaque_tags

    def test_opaque_xml_string_preserved(self, tmp_path):
        path = _write_temp(tmp_path, _MINIMAL_XML)
        project = parse_project(path)
        opaque = next(o for o in project.opaque_elements if o.tag == "unknown_custom_tag")
        assert "unknown_custom_tag" in opaque.xml_string
        assert "some text" in opaque.xml_string


class TestParserGuides:
    def test_guides_parsed(self, tmp_path):
        path = _write_temp(tmp_path, _GUIDE_XML)
        project = parse_project(path)
        assert len(project.guides) == 2
        positions = {g.position for g in project.guides}
        assert 75 in positions
        assert 200 in positions

    def test_guide_label(self, tmp_path):
        path = _write_temp(tmp_path, _GUIDE_XML)
        project = parse_project(path)
        g = next(g for g in project.guides if g.position == 75)
        assert g.label == "Chapter 1"
        assert g.category == "chapter"


class TestParserSampleFixture:
    def test_fixture_parses(self):
        fixture = (
            Path(__file__).parent.parent / "fixtures" / "projects" / "sample_tutorial.kdenlive"
        )
        project = parse_project(fixture)
        assert project.version == "7"
        assert project.title == "Sample Tutorial"
        assert len(project.producers) == 2
        assert len(project.playlists) == 2

    def test_fixture_opaque_preserved(self):
        fixture = (
            Path(__file__).parent.parent / "fixtures" / "projects" / "sample_tutorial.kdenlive"
        )
        project = parse_project(fixture)
        opaque_tags = [o.tag for o in project.opaque_elements]
        assert "kdenlive_custom_element" in opaque_tags

    def test_fixture_opaque_text_preserved(self):
        fixture = (
            Path(__file__).parent.parent / "fixtures" / "projects" / "sample_tutorial.kdenlive"
        )
        project = parse_project(fixture)
        opaque = next(o for o in project.opaque_elements if o.tag == "kdenlive_custom_element")
        assert "preserved as opaque" in opaque.xml_string


class TestParserGracefulFailure:
    def test_nonexistent_file_returns_empty_project(self, tmp_path):
        project = parse_project(tmp_path / "nonexistent.kdenlive")
        assert isinstance(project, KdenliveProject)

    def test_empty_file_returns_empty_project(self, tmp_path):
        p = tmp_path / "empty.kdenlive"
        p.write_text("", encoding="utf-8")
        project = parse_project(p)
        assert isinstance(project, KdenliveProject)


class TestParserPreservesEntryFilters:
    """The parser must round-trip per-entry ``<filter>`` children into
    ``EntryFilter`` model instances so subsequent ``clip_insert`` calls
    don't strip user-added effects.  Patterns covered: audio fade
    (in/out attrs + scalar gain/end), qtblend transform (keyframe rect
    string), effect zones (kdenlive:zone_in/out)."""

    def test_round_trip_audio_fade_in(self, tmp_path):
        from workshop_video_brain.core.models.kdenlive import (
            EntryFilter,
            KdenliveProject,
            Playlist,
            PlaylistEntry,
            Producer,
            ProjectProfile,
            Track,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
            serialize_project,
        )

        # Build a project with one clip carrying a fadein filter.
        project = KdenliveProject(
            version="7", title="round-trip test",
            profile=ProjectProfile(width=1920, height=1080, fps=29.97, colorspace="709"),
            tracks=[Track(id="pl_v", track_type="video")],
            playlists=[Playlist(id="pl_v", entries=[
                PlaylistEntry(
                    producer_id="prod0", in_point=0, out_point=149,
                    filters=[
                        EntryFilter(
                            id="fade_in", in_frame=0, out_frame=14,
                            properties={
                                "mlt_service": "volume",
                                "kdenlive_id": "fadein",
                                "gain": "0",
                                "end": "1",
                            },
                        ),
                    ],
                ),
            ])],
            producers=[
                Producer(
                    id="prod0", resource="/clip.mp4",
                    properties={
                        "resource": "/clip.mp4",
                        "mlt_service": "avformat-novalidate",
                        "length": "150",
                    },
                ),
            ],
            tractor={"id": "t", "in": "0", "out": "149"},
        )

        out_path = tmp_path / "rt.kdenlive"
        serialize_project(project, out_path)

        # Parse it back and verify the filter survived.
        parsed = parse_project(out_path)
        entry = next(e for pl in parsed.playlists for e in pl.entries if e.producer_id)
        assert len(entry.filters) == 1
        f = entry.filters[0]
        assert f.id == "fade_in"
        assert f.in_frame == 0
        assert f.out_frame == 14
        assert f.properties["mlt_service"] == "volume"
        assert f.properties["kdenlive_id"] == "fadein"
        assert f.properties["gain"] == "0"
        assert f.properties["end"] == "1"

    def test_round_trip_effect_zone(self, tmp_path):
        from workshop_video_brain.core.models.kdenlive import (
            EntryFilter,
            KdenliveProject,
            Playlist,
            PlaylistEntry,
            Producer,
            ProjectProfile,
            Track,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
            serialize_project,
        )

        project = KdenliveProject(
            version="7", title="zone test",
            profile=ProjectProfile(width=1920, height=1080, fps=29.97, colorspace="709"),
            tracks=[Track(id="pl_v", track_type="video")],
            playlists=[Playlist(id="pl_v", entries=[
                PlaylistEntry(
                    producer_id="p0", in_point=0, out_point=149,
                    filters=[
                        EntryFilter(
                            id="zone_brightness",
                            zone_in_frame=30,
                            zone_out_frame=89,
                            properties={
                                "mlt_service": "brightness",
                                "kdenlive_id": "brightness",
                                "level": "1.4",
                            },
                        ),
                    ],
                ),
            ])],
            producers=[
                Producer(id="p0", resource="/clip.mp4", properties={
                    "resource": "/clip.mp4",
                    "mlt_service": "avformat-novalidate",
                    "length": "150",
                }),
            ],
        )

        out_path = tmp_path / "zone.kdenlive"
        serialize_project(project, out_path)
        parsed = parse_project(out_path)
        entry = next(e for pl in parsed.playlists for e in pl.entries if e.producer_id)
        assert len(entry.filters) == 1
        f = entry.filters[0]
        assert f.zone_in_frame == 30
        assert f.zone_out_frame == 89
        assert f.properties["mlt_service"] == "brightness"

    def test_round_trip_qtblend_transform(self, tmp_path):
        from workshop_video_brain.core.models.kdenlive import (
            EntryFilter,
            KdenliveProject,
            Playlist,
            PlaylistEntry,
            Producer,
            ProjectProfile,
            Track,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
            serialize_project,
        )

        rect = "00:00:00.000=0 0 1920 1080 1.000000;00:00:01.000=-100 0 2020 1080 1.000000"
        project = KdenliveProject(
            version="7", title="qtblend test",
            profile=ProjectProfile(width=1920, height=1080, fps=29.97, colorspace="709"),
            tracks=[Track(id="pl_v", track_type="video")],
            playlists=[Playlist(id="pl_v", entries=[
                PlaylistEntry(
                    producer_id="p0", in_point=0, out_point=149,
                    filters=[
                        EntryFilter(
                            id="qtblend",
                            properties={
                                "mlt_service": "qtblend",
                                "kdenlive_id": "qtblend",
                                "rect": rect,
                                "rotation": "00:00:00.000=0;00:00:01.000=0",
                                "compositing": "0",
                                "distort": "0",
                                "rotate_center": "1",
                            },
                        ),
                    ],
                ),
            ])],
            producers=[
                Producer(id="p0", resource="/img.png", properties={
                    "resource": "/img.png",
                    "mlt_service": "qimage",
                    "length": "150",
                }),
            ],
        )

        out_path = tmp_path / "qt.kdenlive"
        serialize_project(project, out_path)
        parsed = parse_project(out_path)
        entry = next(e for pl in parsed.playlists for e in pl.entries if e.producer_id)
        assert len(entry.filters) == 1
        # The keyframe string survives intact
        assert entry.filters[0].properties["rect"] == rect
