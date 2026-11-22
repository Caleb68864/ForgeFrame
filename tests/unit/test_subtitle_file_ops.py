"""Subtitle file operations (prompt 37; no ffmpeg)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool
from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import (
    load_cues,
    merge_cues,
    rewrap_cues,
    shift_cues,
    split_cues,
    write_cues,
)
from workshop_video_brain.edit_mcp.server.tools import subtitle_files as tools

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"


def C(a, b, t="x"):
    return SubtitleCue(start_seconds=a, end_seconds=b, text=t)


def spans(cues):
    return [(round(c.start_seconds, 3), round(c.end_seconds, 3)) for c in cues]


def test_shift():
    cues = [C(1.0, 1.5), C(1.0, 3.0), C(12.0, 13.0)]
    assert spans(shift_cues(cues, 1.5)[0]) == [(2.5, 3.0), (2.5, 4.5), (13.5, 14.5)]
    moved, dropped = shift_cues(cues, -2.0)
    assert dropped == 1 and spans(moved)[:1] == [(0.0, 1.0)]
    assert spans(shift_cues(cues, 5.0, from_seconds=10)[0])[:2] == [(1.0, 1.5), (1.0, 3.0)]
    assert shift_cues([C(10.0, 20.0)], scale=25 / 23.976)[0][0].end_seconds == pytest.approx(20 * 25 / 23.976)
    with pytest.raises(ValueError):
        shift_cues(cues, scale=3.0)


def test_merge():
    merged, overlaps = merge_cues([([C(0, 2), C(6, 7)], 0.0), ([C(0, 1.5)], 5.0)])
    assert spans(merged) == [(0, 2), (5, 6.5), (6, 7)] and overlaps == 1


def test_split():
    first, second = split_cues([C(1, 2, "a"), C(3, 5, "b"), C(6, 7, "c")], 4.0)
    assert spans(first) == [(1, 2), (3, 4)] and spans(second) == [(0, 1), (2, 3)]
    assert first[-1].text == second[0].text == "b"


def test_rewrap():
    text = ("word " * 40).strip()  # 199 characters
    cues = rewrap_cues([C(10.0, 20.0, text)], 42, 2)
    assert len(cues) >= 3
    assert cues[0].start_seconds == 10.0 and cues[-1].end_seconds == pytest.approx(20.0, abs=1e-3)
    assert all(a.end_seconds == pytest.approx(b.start_seconds) for a, b in zip(cues, cues[1:]))
    assert all(len(line) <= 42 for c in cues for line in c.text.split("\n"))
    assert all(c.text.count("\n") <= 1 for c in cues)


def test_srt_vtt_srt_round_trip(tmp_path):
    original = load_cues(FIX / "sample.srt")
    write_cues(original, tmp_path / "a.vtt", "vtt")
    write_cues(load_cues(tmp_path / "a.vtt"), tmp_path / "b.srt", "srt")
    back = load_cues(tmp_path / "b.srt")
    assert len(back) == len(original)
    for a, b in zip(original, back):
        assert abs(a.start_seconds - b.start_seconds) < 0.002 and abs(a.end_seconds - b.end_seconds) < 0.002
        assert " ".join(a.text.split()) == " ".join(b.text.split())


def test_ass_output_and_input(tmp_path):
    write_cues([C(0, 1, "hi")], tmp_path / "s.ass", "ass", style={"font": "Liberation Sans"}, width=1280, height=720)
    text = (tmp_path / "s.ass").read_text()
    assert "PlayResX: 1280" in text and "Style: Default,Liberation Sans" in text
    with pytest.raises(ValueError, match="ASS input"):
        load_cues(tmp_path / "s.ass")
    result = call_tool(tools.subtitle_convert, str(tmp_path / "s.ass"), format="srt")
    assert result["error_type"] == "invalid_input"


@pytest.mark.parametrize("call", [
    lambda src, raw: call_tool(tools.subtitle_convert, src, output_dir=raw),
    lambda src, raw: call_tool(tools.subtitle_shift, src, 1.0, output_dir=raw),
    lambda src, raw: call_tool(tools.subtitle_merge, f'["{src}", "{src}"]', output_dir=raw),
    lambda src, raw: call_tool(tools.subtitle_split, src, 2.0, output_dir=raw),
    lambda src, raw: call_tool(tools.subtitle_restyle, src, output_dir=raw),
])
def test_protected_outputs(tmp_path, call):
    raw = tmp_path / "ws" / "media" / "raw"
    raw.mkdir(parents=True)
    result = call(str(FIX / "sample.srt"), str(raw))
    assert result["error_type"] == "invalid_input" and list(raw.iterdir()) == []


def test_tools(tmp_path):
    assert_registered("subtitle_convert", "subtitle_shift", "subtitle_merge", "subtitle_split", "subtitle_restyle",
                      "media_burn_subtitles")
    src = str(FIX / "sample.srt")
    vtt = call_tool(tools.subtitle_convert, src, output_dir=str(tmp_path))
    assert vtt["data"]["output_path"].endswith("sample.vtt")
    split = call_tool(tools.subtitle_split, src, 2.0, output_dir=str(tmp_path))
    assert split["data"]["part1"]["output_path"].endswith("sample_part1.srt")
    styled = call_tool(tools.subtitle_restyle, src, style='{"size": 60}', output_dir=str(tmp_path))
    assert styled["data"]["format"] == "ass"
    assert call_tool(tools.subtitle_merge, "[oops")["error_type"] == "bad_json_param"
    assert call_tool(tools.subtitle_merge, f'["{src}", "{src}"]', offsets="[1]")["error_type"] == "invalid_input"
