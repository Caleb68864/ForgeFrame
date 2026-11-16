"""Kdenlive 26.x writes clip in/out/length as MLT timecode, not frame counts.

Before the fix ``parse_project`` called ``int()`` on ``in="00:00:01.001"``,
logged "Skipping malformed <playlist>", and dropped the playlist (and every
``<chain>``) -- a Kdenlive-saved project lost its whole timeline on import.

``tests/fixtures/projects/real/timecode_2608.kdenlive`` is the document
Kdenlive 26.08.2 itself wrote (``kdenlive --render`` regenerates the project
and writes it as ``kdenlive-*.mlt``; see PROVENANCE.txt) for a 29.97 fps
project with two trimmed clips and a 45-frame gap.  The frame values asserted
below are the ones ForgeFrame put into the project before Kdenlive rewrote it.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

REAL = Path(__file__).resolve().parents[1] / "fixtures" / "projects" / "real"
NATIVE_26 = REAL / "timecode_2608.kdenlive"
NATIVE_25 = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "kdenlive_references" / "single_clip_kdenlive_native.kdenlive"
)

NTSC = 30000 / 1001


def _timeline(project):
    """Non-empty content playlists as (producer-or-gap, in, out) tuples."""
    out = []
    for playlist in project.playlists:
        rows = [(e.producer_id or "<gap>", e.in_point, e.out_point) for e in playlist.entries]
        if rows:
            out.append((playlist.id, rows))
    return out


# --------------------------------------------------------------------------
# The converter
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,fps,frames",
    [
        ("0", 25.0, 0),
        ("137", 25.0, 137),
        ("-1", 25.0, -1),
        ("00:00:00.000", 25.0, 0),
        ("00:00:03.960", 25.0, 99),
        ("00:01:20.487", NTSC, 2412),
        ("00:00:01.001", NTSC, 30),
        ("00:00:01.502", NTSC, 45),
        ("01:00:00.000", 25.0, 90000),
        ("00:00:01,500", 25.0, 38),  # comma decimal (non-C LC_NUMERIC)
        ("00:00:02:05", 25.0, 55),  # SMPTE HH:MM:SS:FF
        ("00:01:00;02", NTSC, 1800),  # drop-frame: first frame of minute 1
        ("00:10:00;00", NTSC, 17982),  # drop-frame: 10th minute drops nothing
    ],
)
def test_mlt_time_to_frames(value, fps, frames):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import mlt_time_to_frames

    assert mlt_time_to_frames(value, fps) == frames


@pytest.mark.parametrize("bad", ["", "abc", "00:xx:01.000", "1:2:3:4:5"])
def test_mlt_time_to_frames_rejects_garbage(bad):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import mlt_time_to_frames

    with pytest.raises(ValueError):
        mlt_time_to_frames(bad, 25.0)


# --------------------------------------------------------------------------
# Real Kdenlive 26.08 document
# --------------------------------------------------------------------------

def test_native_26_timeline_survives_import():
    project = parse_project(NATIVE_26)
    assert project.profile.fps == pytest.approx(NTSC)
    timeline = _timeline(project)
    clips = [("a_bars_9eb3f4", 30, 90), ("<gap>", 0, 44), ("b_blue_efa8ac", 15, 120)]
    # Video and audio lanes both carry the trimmed clips and the 45-frame gap.
    assert len(timeline) == 2, timeline
    for _pid, rows in timeline:
        assert [r[1:] for r in rows] == [c[1:] for c in clips]
    assert [r[0] for r in timeline[0][1]] == [c[0] for c in clips]
    # The bin chains/producers are not dropped either.
    ids = {p.id for p in project.producers}
    assert {"a_bars_9eb3f4", "b_blue_efa8ac"} <= ids


def test_native_26_round_trips_frames(tmp_path):
    project = parse_project(NATIVE_26)
    out = tmp_path / "rt.kdenlive"
    serialize_project(project, out)
    again = parse_project(out)
    assert len(_timeline(project)) == 2
    assert _timeline(again) == _timeline(project)
    assert again.profile.fps == pytest.approx(NTSC)


def test_native_25_chain_and_gap_survive():
    """The Kdenlive 25.08 reference save also uses timecode (chain out, blank)."""
    project = parse_project(NATIVE_25)
    timeline = _timeline(project)
    assert timeline, "native 25.08 save parsed to an empty timeline"
    rows = [row for _pid, rs in timeline for row in rs]
    # <blank length="00:01:20.487"/> at 29.97 fps -> 2412 frames, then the
    # clip 00:00:00.000 .. 00:00:06.073 -> 0 .. 182.
    assert ("<gap>", 0, 2411) in rows
    assert ("chain0", 0, 182) in rows
    assert any(p.id == "chain0" and p.chain_out == 182 for p in project.producers)


def test_timecode_uses_profile_fps_even_when_profile_comes_later(tmp_path):
    doc = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <mlt LC_NUMERIC="C" version="7.42.0">
          <producer id="clip"><property name="resource">a.mp4</property></producer>
          <playlist id="playlist0">
            <blank length="00:00:01.000"/>
            <entry producer="clip" in="00:00:02.000" out="00:00:03.000"/>
          </playlist>
          <profile frame_rate_num="50" frame_rate_den="1" width="1920" height="1080"/>
        </mlt>
        """
    )
    path = tmp_path / "late_profile.kdenlive"
    path.write_text(doc)
    project = parse_project(path)
    assert _timeline(project) == [("playlist0", [("<gap>", 0, 49), ("clip", 100, 150)])]


def test_malformed_time_still_skips_only_that_playlist(tmp_path):
    doc = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <mlt LC_NUMERIC="C" version="7.42.0">
          <profile frame_rate_num="25" frame_rate_den="1" width="1920" height="1080"/>
          <producer id="clip"><property name="resource">a.mp4</property></producer>
          <playlist id="bad"><entry producer="clip" in="nonsense" out="10"/></playlist>
          <playlist id="good"><entry producer="clip" in="00:00:00.000" out="00:00:00.400"/></playlist>
        </mlt>
        """
    )
    path = tmp_path / "mixed.kdenlive"
    path.write_text(doc)
    project = parse_project(path)
    assert _timeline(project) == [("good", [("clip", 0, 10)])]
    assert any('id="bad"' in o.xml_string for o in project.opaque_elements)
