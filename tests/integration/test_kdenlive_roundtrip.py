"""Integration tests: Kdenlive model → serialize → parse → verify equivalence.

Extended with patcher tests: add guides via patcher → serialize → re-parse
→ verify guides and opaque elements are preserved.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddGuide, AddTransition
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
    serialize_versioned,
)


def _make_round_trip_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Round Trip Test",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        producers=[
            Producer(
                id="prod0",
                resource="/media/clip1.mp4",
                properties={"resource": "/media/clip1.mp4", "length": "150"},
            ),
            Producer(
                id="prod1",
                resource="/media/clip2.mp4",
                properties={"resource": "/media/clip2.mp4", "length": "250"},
            ),
        ],
        playlists=[
            Playlist(
                id="pl0",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=149)],
            ),
            Playlist(
                id="pl1",
                entries=[PlaylistEntry(producer_id="prod1", in_point=0, out_point=249)],
            ),
        ],
        tracks=[
            Track(id="pl0", track_type="video"),
            Track(id="pl1", track_type="audio"),
        ],
        tractor={"id": "tractor0", "in": "0", "out": "249"},
        guides=[
            Guide(position=25, label="Intro", category="chapter"),
            Guide(position=100, label="Main part"),
        ],
        opaque_elements=[
            OpaqueElement(
                tag="kdenlive_custom",
                xml_string="<kdenlive_custom>opaque data</kdenlive_custom>",
                position_hint="test",
            )
        ],
    )


class TestRoundTrip:
    def test_title_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert restored.title == original.title

    def test_version_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert restored.version == original.version

    def test_profile_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert restored.profile.width == 1920
        assert restored.profile.height == 1080
        assert restored.profile.fps == 25.0
        assert restored.profile.colorspace == "709"

    def test_producers_count_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert len(restored.producers) == len(original.producers)

    def test_producer_ids_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        original_ids = {p.id for p in original.producers}
        restored_ids = {p.id for p in restored.producers}
        assert original_ids == restored_ids

    def test_producer_resources_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        for orig_p in original.producers:
            restored_p = next(p for p in restored.producers if p.id == orig_p.id)
            assert restored_p.resource == orig_p.resource

    def test_playlists_count_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert len(restored.playlists) == len(original.playlists)

    def test_playlist_entries_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        orig_pl0 = next(pl for pl in original.playlists if pl.id == "pl0")
        rest_pl0 = next(pl for pl in restored.playlists if pl.id == "pl0")
        assert len(rest_pl0.entries) == len(orig_pl0.entries)
        assert rest_pl0.entries[0].producer_id == orig_pl0.entries[0].producer_id
        assert rest_pl0.entries[0].in_point == orig_pl0.entries[0].in_point
        assert rest_pl0.entries[0].out_point == orig_pl0.entries[0].out_point

    def test_guides_count_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        assert len(restored.guides) == len(original.guides)

    def test_guide_positions_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        orig_positions = {g.position for g in original.guides}
        rest_positions = {g.position for g in restored.guides}
        assert orig_positions == rest_positions

    def test_opaque_element_preserved(self, tmp_path):
        original = _make_round_trip_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)
        opaque_tags = [o.tag for o in restored.opaque_elements]
        assert "kdenlive_custom" in opaque_tags
        opaque = next(o for o in restored.opaque_elements if o.tag == "kdenlive_custom")
        assert "opaque data" in opaque.xml_string


class TestRoundTripVersioned:
    def test_versioned_round_trip(self, tmp_path):
        ws = tmp_path / "workspace"
        (ws / "projects" / "working_copies").mkdir(parents=True)
        (ws / "projects" / "snapshots").mkdir(parents=True)

        original = _make_round_trip_project()
        out_path = serialize_versioned(original, ws, "round_trip")
        assert out_path.exists()

        restored = parse_project(out_path)
        assert restored.title == original.title
        assert len(restored.producers) == len(original.producers)


class TestPatcherRoundTrip:
    """Verify guides added via patcher survive serialize → re-parse."""

    def test_add_guide_via_patcher_survives_round_trip(self, tmp_path):
        """Add a guide through patcher, serialize, re-parse; guide must be present."""
        original = _make_round_trip_project()
        intents = [
            AddGuide(position_frames=50, label="Patched Guide", category="chapter"),
        ]
        patched = patch_project(original, intents)
        assert any(g.label == "Patched Guide" for g in patched.guides)

        out = tmp_path / "patched.kdenlive"
        serialize_project(patched, out)
        restored = parse_project(out)

        guide_labels = [g.label for g in restored.guides]
        assert "Patched Guide" in guide_labels

    def test_multiple_guides_added_all_survive(self, tmp_path):
        original = _make_round_trip_project()
        intents = [
            AddGuide(position_frames=10, label="Guide A", category="chapter"),
            AddGuide(position_frames=200, label="Guide B", category="section"),
            AddGuide(position_frames=500, label="Guide C"),
        ]
        patched = patch_project(original, intents)
        assert len(patched.guides) == len(original.guides) + 3

        out = tmp_path / "multi_guides.kdenlive"
        serialize_project(patched, out)
        restored = parse_project(out)

        labels = {g.label for g in restored.guides}
        assert "Guide A" in labels
        assert "Guide B" in labels
        assert "Guide C" in labels

    def test_opaque_elements_preserved_after_patcher(self, tmp_path):
        """Opaque elements must survive patcher → serialize → re-parse."""
        original = _make_round_trip_project()
        intents = [AddGuide(position_frames=75, label="Test Guide")]
        patched = patch_project(original, intents)

        out = tmp_path / "opaque_check.kdenlive"
        serialize_project(patched, out)
        restored = parse_project(out)

        opaque_tags = [o.tag for o in restored.opaque_elements]
        assert "kdenlive_custom" in opaque_tags

    def test_add_transition_creates_opaque_element(self, tmp_path):
        """AddTransition intent creates an opaque transition element."""
        original = _make_round_trip_project()
        intents = [
            AddTransition(
                type="luma",
                track_ref="pl0",
                left_clip_ref="prod0",
                right_clip_ref="prod1",
                duration_frames=12,
            )
        ]
        patched = patch_project(original, intents)
        transition_opaques = [
            o for o in patched.opaque_elements if o.tag == "transition"
        ]
        assert len(transition_opaques) >= 1

    def test_transition_opaque_survives_round_trip(self, tmp_path):
        """Transition opaque element must survive serialize → re-parse."""
        original = _make_round_trip_project()
        intents = [
            AddTransition(
                type="luma",
                track_ref="pl0",
                left_clip_ref="prod0",
                right_clip_ref="prod1",
                duration_frames=24,
            )
        ]
        patched = patch_project(original, intents)
        out = tmp_path / "transition_rt.kdenlive"
        serialize_project(patched, out)
        restored = parse_project(out)

        transition_opaques = [o for o in restored.opaque_elements if o.tag == "transition"]
        assert len(transition_opaques) >= 1

    def test_patch_does_not_mutate_original(self, tmp_path):
        """patch_project must not mutate the source project."""
        original = _make_round_trip_project()
        original_guide_count = len(original.guides)
        intents = [AddGuide(position_frames=99, label="Should Not Appear In Original")]
        _patched = patch_project(original, intents)
        assert len(original.guides) == original_guide_count


class TestSampleFixtureRoundTrip:
    def test_fixture_round_trip(self, tmp_path):
        fixture = (
            Path(__file__).parent.parent / "fixtures" / "projects" / "sample_tutorial.kdenlive"
        )
        original = parse_project(fixture)

        out = tmp_path / "fixture_rt.kdenlive"
        serialize_project(original, out)
        restored = parse_project(out)

        assert restored.title == original.title
        assert len(restored.producers) == len(original.producers)
        # Opaque element from fixture must survive
        orig_opaque_tags = {o.tag for o in original.opaque_elements}
        rest_opaque_tags = {o.tag for o in restored.opaque_elements}
        assert orig_opaque_tags.issubset(rest_opaque_tags)
