"""Unit tests for the pure clip-placement engine (``pipelines.clip_place``).

Covers the placement math directly: overlap-splitting cases (clip fully inside an
existing entry, spanning two entries, over blanks, at frame 0, beyond the end),
insert/ripple behaviour, index remapping, and the fractional-fps rounding tables
(23.976 / 29.97). No I/O, no melt.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.core.models.kdenlive import PlaylistEntry
from workshop_video_brain.edit_mcp.pipelines import clip_place as cp


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _spans(entries):
    """(producer_id_or_'', timeline_start, timeline_end, in_point, out_point) rows."""
    rows = []
    s = 0
    for e in entries:
        length = cp.entry_length(e)
        rows.append((e.producer_id, s, s + length, e.in_point, e.out_point))
        s += length
    return rows


def _clip(pid, length):
    return cp.PlacedClip(producer_id=pid, in_point=0, out_point=length - 1)


RED = [PlaylistEntry(producer_id="red", in_point=0, out_point=99)]  # 100 frames


# ---------------------------------------------------------------------------
# seconds_to_frames -- fractional-fps rounding tables
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "seconds,fps,expected",
    [
        # integer fps
        (0.0, 25.0, 0),
        (1.0, 25.0, 25),
        (2.0, 25.0, 50),
        (1.96, 25.0, 49),   # 49.0 -> 49
        # 23.976 NTSC film
        (1.0, 23.976, 24),   # 23.976 -> 24 (half-up)
        (2.0, 23.976, 48),   # 47.952 -> 48
        (0.5, 23.976, 12),   # 11.988 -> 12
        (10.0, 23.976, 240),  # 239.76 -> 240
        # 29.97 NTSC video
        (1.0, 29.97, 30),    # 29.97 -> 30
        (2.0, 29.97, 60),    # 59.94 -> 60
        (2.5, 29.97, 75),    # 74.925 -> 75
        (0.1, 29.97, 3),     # 2.997 -> 3
    ],
)
def test_seconds_to_frames_rounding(seconds, fps, expected):
    assert cp.seconds_to_frames(seconds, fps) == expected


def test_seconds_to_frames_rejects_negative_and_bad_fps():
    with pytest.raises(ValueError):
        cp.seconds_to_frames(-1.0, 25.0)
    with pytest.raises(ValueError):
        cp.seconds_to_frames(1.0, 0.0)


# ---------------------------------------------------------------------------
# overwrite -- overlap-splitting cases
# ---------------------------------------------------------------------------

def test_overwrite_clip_fully_inside_existing_entry():
    # region [50,75) sits entirely inside the 100-frame red clip.
    r = cp.plan_overwrite(RED, 50, _clip("blue", 25))
    assert _spans(r.entries) == [
        ("red", 0, 50, 0, 49),     # left remainder keeps source 0..49
        ("blue", 50, 75, 0, 24),   # placed clip
        ("red", 75, 100, 75, 99),  # right fragment continues source at 75
    ]
    assert r.index_map == {0: 0}     # original red keeps identity on the left
    assert r.placed_index == 1


def test_overwrite_at_frame_zero():
    r = cp.plan_overwrite(RED, 0, _clip("blue", 25))
    assert _spans(r.entries) == [
        ("blue", 0, 25, 0, 24),
        ("red", 25, 100, 25, 99),
    ]
    assert r.index_map == {0: 1}
    assert r.placed_index == 0


def test_overwrite_spanning_two_entries():
    two = [
        PlaylistEntry(producer_id="red", in_point=0, out_point=49),    # [0,50)
        PlaylistEntry(producer_id="green", in_point=0, out_point=49),  # [50,100)
    ]
    r = cp.plan_overwrite(two, 40, _clip("blue", 30))  # region [40,70)
    assert _spans(r.entries) == [
        ("red", 0, 40, 0, 39),
        ("blue", 40, 70, 0, 29),
        ("green", 70, 100, 20, 49),  # green tail continues at source 20
    ]
    assert r.index_map == {0: 0, 1: 2}
    assert r.placed_index == 1


def test_overwrite_covers_entire_entry_drops_it():
    two = [
        PlaylistEntry(producer_id="red", in_point=0, out_point=24),   # [0,25)
        PlaylistEntry(producer_id="green", in_point=0, out_point=24),  # [25,50)
    ]
    r = cp.plan_overwrite(two, 25, _clip("blue", 25))  # region [25,50) == green
    assert _spans(r.entries) == [
        ("red", 0, 25, 0, 24),
        ("blue", 25, 50, 0, 24),
    ]
    assert r.index_map == {0: 0, 1: None}  # green overwritten
    assert r.placed_index == 1


def test_overwrite_over_a_blank():
    with_blank = [
        PlaylistEntry(producer_id="red", in_point=0, out_point=24),  # [0,25)
        PlaylistEntry(producer_id="", in_point=0, out_point=49),     # blank [25,75)
        PlaylistEntry(producer_id="green", in_point=0, out_point=24),  # [75,100)
    ]
    r = cp.plan_overwrite(with_blank, 40, _clip("blue", 20))  # region [40,60) inside blank
    assert _spans(r.entries) == [
        ("red", 0, 25, 0, 24),
        ("", 25, 40, 0, 14),    # blank left remainder (15 frames)
        ("blue", 40, 60, 0, 19),
        ("", 60, 75, 0, 14),    # blank right remainder (15 frames)
        ("green", 75, 100, 0, 24),
    ]
    assert r.index_map == {0: 0, 1: 2}  # green pushed to index 2 by placed blue


def test_overwrite_beyond_end_pads_blank():
    r = cp.plan_overwrite(RED, 120, _clip("blue", 25))  # 20-frame gap first
    assert _spans(r.entries) == [
        ("red", 0, 100, 0, 99),
        ("", 100, 120, 0, 19),
        ("blue", 120, 145, 0, 24),
    ]
    assert r.placed_index == 1


def test_overwrite_extends_past_end_no_right_fragment():
    # region starts inside content but ends past it -> right side is empty.
    r = cp.plan_overwrite(RED, 90, _clip("blue", 30))  # [90,120)
    assert _spans(r.entries) == [
        ("red", 0, 90, 0, 89),
        ("blue", 90, 120, 0, 29),
    ]
    assert r.index_map == {0: 0}


# ---------------------------------------------------------------------------
# insert -- ripple this track
# ---------------------------------------------------------------------------

def test_insert_mid_ripples_tail_right():
    r = cp.plan_insert(RED, 50, _clip("blue", 25))
    assert _spans(r.entries) == [
        ("red", 0, 50, 0, 49),
        ("blue", 50, 75, 0, 24),
        ("red", 75, 125, 50, 99),  # tail keeps its source frames, moved later
    ]
    assert cp.playlist_length(r.entries) == 125  # grew by clip length
    assert r.placed_index == 1


def test_insert_at_zero_prepends():
    r = cp.plan_insert(RED, 0, _clip("blue", 25))
    assert _spans(r.entries) == [
        ("blue", 0, 25, 0, 24),
        ("red", 25, 125, 0, 99),
    ]
    assert r.index_map == {0: 1}


def test_insert_beyond_end_pads():
    r = cp.plan_insert(RED, 130, _clip("blue", 25))
    assert _spans(r.entries) == [
        ("red", 0, 100, 0, 99),
        ("", 100, 130, 0, 29),
        ("blue", 130, 155, 0, 24),
    ]


def test_insert_blank_ripples_other_track():
    other = [PlaylistEntry(producer_id="a", in_point=0, out_point=99)]
    out = cp.plan_insert_blank(other, 40, 25)
    assert _spans(out) == [
        ("a", 0, 40, 0, 39),
        ("", 40, 65, 0, 24),
        ("a", 65, 125, 40, 99),
    ]


def test_insert_blank_short_track_unchanged():
    other = [PlaylistEntry(producer_id="a", in_point=0, out_point=29)]  # 30 frames
    out = cp.plan_insert_blank(other, 40, 25)  # insertion point past end
    assert _spans(out) == _spans(other)


# ---------------------------------------------------------------------------
# reference helpers + validation
# ---------------------------------------------------------------------------

def test_reference_length_and_start():
    entries = [
        PlaylistEntry(producer_id="", in_point=0, out_point=9),      # blank 10
        PlaylistEntry(producer_id="a", in_point=0, out_point=39),    # [10,50)
        PlaylistEntry(producer_id="b", in_point=0, out_point=19),    # [50,70)
    ]
    assert cp.reference_length(entries, 0) == 40
    assert cp.clip_start_frame(entries, 0) == 10
    assert cp.reference_length(entries, 1) == 20
    assert cp.clip_start_frame(entries, 1) == 50


def test_clip_at_index_out_of_range():
    with pytest.raises(IndexError):
        cp.clip_at_index(RED, 5)


def test_plan_rejects_bad_input():
    with pytest.raises(ValueError):
        cp.plan_overwrite(RED, -1, _clip("blue", 10))
    with pytest.raises(ValueError):
        cp.plan_overwrite(RED, 10, cp.PlacedClip("x", 5, 4))  # zero/neg length
    with pytest.raises(ValueError):
        cp.plan_insert(RED, -5, _clip("blue", 10))
