"""Text-based editing: deletions -> keep ranges -> retimed transcript (prompt 38; pure)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming
from workshop_video_brain.edit_mcp.pipelines import text_edit

WORDS = ["Um,", "the", "zipper", "goes", "on", "the", "left", "you", "know", "um."]


def transcript(words=WORDS):
    wt = [WordTiming(word=w, start=0.5 * i, end=0.5 * i + 0.4) for i, w in enumerate(words)]
    return Transcript(asset_id=uuid4(), segments=[
        TranscriptSegment(start_seconds=0.0, end_seconds=2.4, text=" ".join(words[:5]), words=wt[:5]),
        TranscriptSegment(start_seconds=2.5, end_seconds=4.9, text=" ".join(words[5:]), words=wt[5:])])


def units():
    return text_edit.units_of(transcript())[0]


def test_cut_runs_between_padded_neighbours():
    deleted = text_edit.select_deletions(units(), [{"words": [3, 5]}])
    ranges = text_edit.keep_ranges(units(), deleted, 5.0, pad=0.05)
    assert ranges == [(0.0, 1.45), (2.95, 5.0)]
    assert text_edit.edit_summary(ranges, 5.0)["removed_seconds"] == pytest.approx(1.5)


def test_cuts_at_the_ends():
    assert text_edit.keep_ranges(units(), {0}, 5.0)[0][0] == pytest.approx(0.45)
    assert text_edit.keep_ranges(units(), {9}, 5.0)[-1][1] == pytest.approx(4.45)


def test_text_and_time_selection():
    u = units()
    assert text_edit.select_deletions(u, [{"text": "um"}]) == {0, 9}
    assert text_edit.select_deletions(u, [{"text": "you know"}]) == {7, 8}
    assert text_edit.select_deletions(u, [{"text": "know you"}]) == set()
    assert text_edit.select_deletions(u, [{"time": [1.0, 2.0]}]) == {2, 3}
    assert text_edit.select_deletions(u, [], remove_fillers=True) == {0, 9}


@pytest.mark.parametrize("bad", [[{"word": [1, 2]}], [{"words": [5, 99]}], [{"segment": 7}], ["x"]])
def test_bad_items(bad):
    with pytest.raises(ValueError):
        text_edit.select_deletions(units(), bad)


def test_remap_and_retime():
    ranges = [(0.0, 1.45), (2.95, 5.0)]
    assert text_edit.remap_time(2.0, ranges) is None
    assert text_edit.remap_time(3.0, ranges) == pytest.approx(1.5)
    retimed = text_edit.retime_transcript(transcript(), ranges, {3, 4, 5})
    texts = [s.text for s in retimed.segments]
    assert texts == ["Um, the zipper", "left you know um."]
    assert retimed.segments[1].start_seconds == pytest.approx(1.5)


def test_segment_granularity(tmp_path):
    t = Transcript(asset_id=uuid4(), segments=[TranscriptSegment(start_seconds=0, end_seconds=2, text="one"),
                                               TranscriptSegment(start_seconds=2, end_seconds=4, text="two")])
    u, granularity = text_edit.units_of(t)
    assert granularity == "segment" and len(u) == 2
    ranges = text_edit.keep_ranges(u, {1}, 4.0)
    assert ranges == [(0.0, 2.05)]
    view, nxt = text_edit.numbered_view(u)
    assert view == "S0 [0] one\nS1 [1] two" and nxt is None


def test_min_keep_drops_slivers():
    # Deleting 3 and 5 leaves word 4 (2.0-2.4) as a 0.5 s island (1.95-2.45 with padding).
    ranges = text_edit.keep_ranges(units(), {3, 5}, 5.0, pad=0.05, min_keep=0.6)
    assert all(e - s >= 0.6 for s, e in ranges)
    assert len(ranges) == 2
