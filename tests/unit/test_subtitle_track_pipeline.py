"""Unit tests for the pure subtitle-track pipeline.

Covers ASS style generation, SRT→ASS conversion, subtitlesList docproperties
assembly, colour conversion, style coercion and project attachment -- none of
which touch melt/ffmpeg, so they run everywhere.
"""
from __future__ import annotations

import json

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    ProjectProfile,
)
from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.edit_mcp.pipelines import subtitle_track as st


# ---------------------------------------------------------------------------
# Colour + time
# ---------------------------------------------------------------------------

def test_hex_to_ass_color_abgr_order():
    # #RRGGBB -> &H00BBGGRR (opaque ABGR)
    assert st.hex_to_ass_color("#FF0000") == "&H000000FF"  # red
    assert st.hex_to_ass_color("#00FF00") == "&H0000FF00"  # green
    assert st.hex_to_ass_color("#0000FF") == "&H00FF0000"  # blue
    assert st.hex_to_ass_color("#FFFF00") == "&H0000FFFF"  # yellow
    assert st.hex_to_ass_color("FFFFFF") == "&H00FFFFFF"   # no leading #


def test_hex_to_ass_color_invalid():
    with pytest.raises(ValueError):
        st.hex_to_ass_color("nope")
    with pytest.raises(ValueError):
        st.hex_to_ass_color("#FFF")


def test_ass_timestamp():
    assert st.ass_timestamp(0) == "0:00:00.00"
    assert st.ass_timestamp(65.5) == "0:01:05.50"
    assert st.ass_timestamp(3661.23) == "1:01:01.23"
    assert st.ass_timestamp(-5) == "0:00:00.00"


# ---------------------------------------------------------------------------
# Style generation
# ---------------------------------------------------------------------------

def test_build_ass_style_line_defaults():
    line = st.build_ass_style_line(st.SubtitleStyle())
    assert line.startswith("Style: Default,DejaVu Sans,48,&H00FFFFFF,")
    # bold flag off, alignment 2 (bottom centre), integral outline 2
    assert line.endswith(",2,10,10,20,1")


def test_build_ass_style_line_custom():
    style = st.SubtitleStyle(
        font="Arial", size=60, primary_color="#FFFF00", bold=True,
        alignment=8, margin_v=40, outline=3,
    )
    line = st.build_ass_style_line(style)
    assert "Arial,60,&H0000FFFF" in line
    assert ",-1,0," in line          # bold=-1, italic=0
    assert line.endswith(",8,10,10,40,1")


# ---------------------------------------------------------------------------
# SRT -> ASS conversion
# ---------------------------------------------------------------------------

SRT = (
    "1\n00:00:00,000 --> 00:00:02,500\nHello world\n\n"
    "2\n00:00:02,500 --> 00:00:05,000\nLine one\nLine two\n"
)


def test_cues_to_ass_structure():
    cues = [
        SubtitleCue(start_seconds=0.0, end_seconds=2.5, text="Hi"),
        SubtitleCue(start_seconds=2.5, end_seconds=5.0, text="Bye"),
    ]
    ass = st.cues_to_ass(cues, width=640, height=360)
    assert "[Script Info]" in ass
    assert "PlayResX: 640" in ass
    assert "PlayResY: 360" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert ass.count("Dialogue:") == 2
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,Hi" in ass


def test_srt_to_ass_multiline_uses_hard_break():
    ass = st.srt_to_ass(SRT, style=st.SubtitleStyle(size=30), width=1920, height=1080)
    assert ass.count("Dialogue:") == 2
    assert "Line one\\NLine two" in ass  # SRT newline -> ASS \N
    assert "DejaVu Sans,30," in ass


# ---------------------------------------------------------------------------
# SubtitleStyle coercion
# ---------------------------------------------------------------------------

def test_style_from_input_variants():
    assert st.SubtitleStyle.from_input(None) is None
    assert st.SubtitleStyle.from_input("") is None
    assert st.SubtitleStyle.from_input("   ") is None

    from_dict = st.SubtitleStyle.from_input({"size": 72})
    assert from_dict.size == 72

    from_json = st.SubtitleStyle.from_input('{"primary_color": "#FF0000"}')
    assert from_json.primary_color == "#FF0000"

    same = st.SubtitleStyle(size=10)
    assert st.SubtitleStyle.from_input(same) is same


def test_style_from_input_position_maps_to_alignment():
    assert st.SubtitleStyle.from_input({"position": "top"}).alignment == 8
    assert st.SubtitleStyle.from_input({"position": "bottom-left"}).alignment == 1
    assert st.SubtitleStyle.from_input({"position": 5}).alignment == 5
    with pytest.raises(ValueError):
        st.SubtitleStyle.from_input({"position": "nowhere"})


def test_style_from_input_bad_type():
    with pytest.raises(ValueError):
        st.SubtitleStyle.from_input(123)


# ---------------------------------------------------------------------------
# Attachment + docproperties assembly
# ---------------------------------------------------------------------------

def _project() -> KdenliveProject:
    return KdenliveProject(
        version="7", title="t",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
    )


def test_attach_subtitle_adds_track():
    p = st.attach_subtitle(_project(), "/tmp/a/proj.kdenlive.ass", name="en")
    assert len(p.subtitles) == 1
    sub = p.subtitles[0]
    assert sub.id == 0
    assert sub.name == "en"
    assert sub.file == "/tmp/a/proj.kdenlive.ass"


def test_attach_subtitle_replace_is_idempotent():
    p = st.attach_subtitle(_project(), "/tmp/a.ass", name="en")
    p2 = st.attach_subtitle(p, "/tmp/b.ass", name="fr")
    # replace=True by default -> single track, not stacking
    assert len(p2.subtitles) == 1
    assert p2.subtitles[0].file == "/tmp/b.ass"


def test_attach_subtitle_append():
    p = st.attach_subtitle(_project(), "/tmp/a.ass", name="en")
    p2 = st.attach_subtitle(p, "/tmp/b.ass", name="fr", replace=False)
    assert len(p2.subtitles) == 2
    assert [s.id for s in p2.subtitles] == [0, 1]


def test_subtitles_list_json_shape():
    p = st.attach_subtitle(_project(), "/abs/path/proj.kdenlive.ass", name="en")
    data = json.loads(st.subtitles_list_json(p))
    assert data == [{"name": "en", "id": 0, "file": "proj.kdenlive.ass"}]
    assert st.active_subtitle_index(p) == "0"


def test_active_subtitle_index_empty():
    assert st.active_subtitle_index(_project()) == "0"


# ---------------------------------------------------------------------------
# force_style + latest_srt
# ---------------------------------------------------------------------------

def test_force_style_string():
    s = st.force_style_string(st.SubtitleStyle(size=30, primary_color="#FFFF00"))
    assert "Fontsize=30" in s
    assert "PrimaryColour=&H0000FFFF" in s
    assert "Alignment=2" in s


def test_latest_srt_picks_newest(tmp_path):
    import os
    import time
    reports = tmp_path / "reports"
    reports.mkdir()
    old = reports / "old.srt"
    new = reports / "new.srt"
    old.write_text("1\n", encoding="utf-8")
    time.sleep(0.01)
    new.write_text("2\n", encoding="utf-8")
    os.utime(old, (1, 1))  # force old mtime
    assert st.latest_srt(reports) == new
    assert st.latest_srt(tmp_path / "missing") is None
