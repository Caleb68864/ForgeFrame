"""Unit tests for the voiceover-loop pipeline (pure logic; no ffmpeg)."""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines import vo_loop as vo


# ---------------------------------------------------------------------------
# Script splitting
# ---------------------------------------------------------------------------

def test_split_script_by_headings():
    text = (
        "# Intro\nWelcome to the build.\n\n"
        "# Materials\nGrab the plywood and glue.\n\n"
        "# Wrap Up\nThanks for watching."
    )
    sections = vo.split_script(text)
    assert [s["heading"] for s in sections] == ["Intro", "Materials", "Wrap Up"]
    assert sections[0]["text"] == "Welcome to the build."


def test_split_script_by_blank_lines_when_no_headings():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird one."
    sections = vo.split_script(text)
    assert len(sections) == 3
    assert all(s["heading"] == "" for s in sections)
    assert sections[1]["text"] == "Second paragraph here."


def test_split_script_heading_with_no_body_uses_heading_text():
    sections = vo.split_script("# Just A Title")
    assert len(sections) == 1
    assert sections[0]["heading"] == "Just A Title"
    assert sections[0]["text"] == "Just A Title"


def test_split_script_preamble_before_first_heading():
    sections = vo.split_script("Opening line.\n\n# Heading\nBody.")
    assert len(sections) == 2
    assert sections[0]["text"] == "Opening line."
    assert sections[1]["heading"] == "Heading"


def test_split_script_empty_returns_nothing():
    assert vo.split_script("") == []
    assert vo.split_script("\n\n  \n") == []


# ---------------------------------------------------------------------------
# Word count + wpm math
# ---------------------------------------------------------------------------

def test_word_count_basic():
    assert vo.word_count("one two three") == 3
    assert vo.word_count("") == 0


def test_word_count_strips_markdown_syntax():
    # Markdown punctuation-only tokens are not words.
    assert vo.word_count("# Heading with **bold** text") == 4


def test_estimate_seconds_matches_wpm_formula():
    # 150 words at 150 wpm == exactly 60 seconds.
    assert vo.estimate_seconds(150, 150) == 60.0
    # 300 words at 150 wpm == 120 seconds.
    assert vo.estimate_seconds(300, 150) == 120.0
    # Double the pace, half the time.
    assert vo.estimate_seconds(150, 300) == 30.0


def test_estimate_seconds_defaults_bad_wpm():
    assert vo.estimate_seconds(150, 0) == 60.0
    assert vo.estimate_seconds(150, -5) == 60.0


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------

def test_build_plan_cumulative_timestamps():
    # Two cues of 150 words each at 150 wpm -> 60s apiece, back to back.
    words = " ".join(["word"] * 150)
    text = f"# A\n{words}\n\n# B\n{words}"
    plan = vo.build_plan(text, wpm=150)
    assert plan["cue_count"] == 2
    a, b = plan["cues"]
    assert a["cue_id"] == "cue_01"
    assert a["est_seconds"] == 60.0
    assert a["start_seconds"] == 0.0
    assert a["end_seconds"] == 60.0
    assert b["start_seconds"] == 60.0
    assert b["end_seconds"] == 120.0
    assert plan["total_est_seconds"] == 120.0


def test_build_plan_ids_zero_padded_and_ordered():
    text = "\n\n".join(f"paragraph number {i}" for i in range(3))
    plan = vo.build_plan(text)
    assert [c["cue_id"] for c in plan["cues"]] == ["cue_01", "cue_02", "cue_03"]


def test_format_checklist_lists_every_cue():
    plan = vo.build_plan("# A\nhello world\n\n# B\ngoodbye world")
    md = vo.format_checklist(plan, script_name="script.md")
    assert "Voiceover Recording Checklist" in md
    assert "cue_01" in md and "cue_02" in md
    assert "script.md" in md


# ---------------------------------------------------------------------------
# Drift reporting
# ---------------------------------------------------------------------------

def test_compute_drift_no_takes_is_zero():
    plan = vo.build_plan("# A\n" + " ".join(["w"] * 150) + "\n\n# B\nmore words here")
    drift = vo.compute_drift(plan)
    assert all(d["drift_seconds"] == 0.0 for d in drift)


def test_compute_drift_accumulates_after_recorded_take():
    words = " ".join(["word"] * 150)  # 60s each
    plan = vo.build_plan(f"# A\n{words}\n\n# B\n{words}\n\n# C\n{words}", wpm=150)
    # Cue A recorded 10s longer than estimated.
    plan["cues"][0]["actual_seconds"] = 70.0
    drift = vo.compute_drift(plan)
    assert drift[0]["drift_seconds"] == 0.0            # A itself unshifted
    assert drift[1]["drift_seconds"] == 10.0           # B shifts by +10
    assert drift[1]["rippled_start_seconds"] == 70.0   # 60 planned + 10 drift
    assert drift[2]["drift_seconds"] == 10.0           # C also +10 (B on estimate)


def test_seconds_to_frames_rounds():
    assert vo.seconds_to_frames(1.0, 30.0) == 30
    assert vo.seconds_to_frames(0.51, 30.0) == 15
    assert vo.seconds_to_frames(2.0, 0) == 50  # bad fps -> DEFAULT_FPS 25
