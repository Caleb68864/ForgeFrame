"""Unit tests for the multicam orchestration pipeline (pure logic).

Covers source/cut argument parsing, offset->leading-gap alignment math, switch
segment expansion, and per-frame source location.  No ffmpeg / melt / project I/O.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.core.models.kdenlive import PlaylistEntry
from workshop_video_brain.edit_mcp.pipelines import multicam as mc


# ---------------------------------------------------------------------------
# parse_source_list
# ---------------------------------------------------------------------------

def test_parse_sources_comma_and_newline():
    assert mc.parse_source_list("a.mp4, b.mp4") == ["a.mp4", "b.mp4"]
    assert mc.parse_source_list("a.mp4\nb.mp4\n") == ["a.mp4", "b.mp4"]


def test_parse_sources_json_array():
    assert mc.parse_source_list('["x.mp4", "y.mp4"]') == ["x.mp4", "y.mp4"]


def test_parse_sources_native_list():
    assert mc.parse_source_list(["p", "q"]) == ["p", "q"]


def test_parse_sources_empty_raises():
    for bad in ("", "   ", ",,", "[]", []):
        with pytest.raises(ValueError):
            mc.parse_source_list(bad)


# ---------------------------------------------------------------------------
# parse_cuts
# ---------------------------------------------------------------------------

def test_parse_cuts_json():
    cuts = mc.parse_cuts('[{"at_seconds": 0, "angle": 0}, {"at_seconds": 2.0, "angle": 1}]')
    assert cuts == [mc.Cut(0.0, 0), mc.Cut(2.0, 1)]


def test_parse_cuts_accepts_aliases():
    cuts = mc.parse_cuts([{"t": 1.5, "track": 2}])
    assert cuts == [mc.Cut(1.5, 2)]


@pytest.mark.parametrize("bad", [
    "",
    "not json",
    "[]",
    '[{"angle": 0}]',            # missing time
    '[{"at_seconds": 1}]',       # missing angle
    '[{"at_seconds": -1, "angle": 0}]',
    '[{"at_seconds": 1, "angle": -1}]',
    '[1, 2, 3]',                 # not objects
])
def test_parse_cuts_bad_raises(bad):
    with pytest.raises(ValueError):
        mc.parse_cuts(bad)


# ---------------------------------------------------------------------------
# parse_int_list
# ---------------------------------------------------------------------------

def test_parse_int_list_forms():
    assert mc.parse_int_list("3,4,5") == [3, 4, 5]
    assert mc.parse_int_list("[1, 2]") == [1, 2]
    assert mc.parse_int_list([0, 7]) == [0, 7]
    assert mc.parse_int_list("") == []
    assert mc.parse_int_list(None) == []


# ---------------------------------------------------------------------------
# compute_alignment
# ---------------------------------------------------------------------------

def test_alignment_reference_only_zero():
    assert mc.compute_alignment([0.0], 25.0) == [0]


def test_alignment_later_angle_gets_smaller_gap():
    # angle 1 event is +2.0s later into its file (extra lead-in) => it must start
    # earlier on the timeline => gap 0, while the reference is pushed right by 2s.
    assert mc.compute_alignment([0.0, 2.0], 25.0) == [50, 0]


def test_alignment_earlier_angle_gets_larger_gap():
    # angle 1 event is 1.0s earlier in its file (started rolling later) => gap +1s.
    assert mc.compute_alignment([0.0, -1.0], 25.0) == [0, 25]


def test_alignment_shared_event_lands_on_same_frame():
    # reference event at 1.0s, angle event at 3.0s (offset +2.0). With the gaps,
    # the event lands at the same absolute timeline frame on both tracks.
    fps = 25.0
    gaps = mc.compute_alignment([0.0, 2.0], fps)
    ref_event_frame = gaps[0] + round(1.0 * fps)
    ang_event_frame = gaps[1] + round(3.0 * fps)
    assert ref_event_frame == ang_event_frame == 75


def test_alignment_all_gaps_non_negative():
    gaps = mc.compute_alignment([0.0, 1.3, -0.7, 2.5], 30.0)
    assert all(g >= 0 for g in gaps)


def test_alignment_bad_fps_raises():
    with pytest.raises(ValueError):
        mc.compute_alignment([0.0], 0.0)


# ---------------------------------------------------------------------------
# build_switch_segments
# ---------------------------------------------------------------------------

def test_segments_expand_to_next_cut_and_timeline_end():
    cuts = [mc.Cut(0.0, 0), mc.Cut(2.0, 1)]
    segs = mc.build_switch_segments(cuts, timeline_end=125, fps=25.0)
    assert segs == [
        mc.Segment(0, 50, 0),
        mc.Segment(50, 125, 1),
    ]


def test_segments_sorts_unordered_cuts():
    cuts = [mc.Cut(2.0, 1), mc.Cut(0.0, 0)]
    segs = mc.build_switch_segments(cuts, timeline_end=100, fps=25.0)
    assert [s.angle for s in segs] == [0, 1]
    assert segs[0].start_frame == 0 and segs[1].start_frame == 50


def test_segments_drops_cut_past_end():
    cuts = [mc.Cut(0.0, 0), mc.Cut(10.0, 1)]  # 10s cut is past a 4s timeline
    segs = mc.build_switch_segments(cuts, timeline_end=100, fps=25.0)
    assert segs == [mc.Segment(0, 100, 0)]


def test_segments_empty_timeline_raises():
    with pytest.raises(ValueError):
        mc.build_switch_segments([mc.Cut(0.0, 0)], timeline_end=0, fps=25.0)


# ---------------------------------------------------------------------------
# locate_source
# ---------------------------------------------------------------------------

def _entries():
    # blank [0,50), red [50,100), green [100,150)
    return [
        PlaylistEntry(producer_id="", in_point=0, out_point=49),
        PlaylistEntry(producer_id="red", in_point=10, out_point=59),   # 50 frames
        PlaylistEntry(producer_id="green", in_point=0, out_point=49),
    ]


def test_locate_source_in_first_real_clip():
    ref = mc.locate_source(_entries(), 60)  # 10 into the red clip (timeline 50)
    assert ref is not None
    assert ref.producer_id == "red"
    assert ref.in_point == 10 + (60 - 50)   # entry in-point + offset into clip
    assert ref.available_end == 100


def test_locate_source_in_blank_returns_none():
    assert mc.locate_source(_entries(), 10) is None


def test_locate_source_past_end_returns_none():
    assert mc.locate_source(_entries(), 999) is None


def test_locate_source_second_clip():
    ref = mc.locate_source(_entries(), 120)
    assert ref is not None and ref.producer_id == "green"
    assert ref.in_point == 0 + (120 - 100)
    assert ref.available_end == 150
