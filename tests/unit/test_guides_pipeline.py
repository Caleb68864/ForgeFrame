"""Unit tests for the pure guide + chapter pipeline helpers."""
from __future__ import annotations

import json

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    ProjectProfile,
)
from workshop_video_brain.edit_mcp.pipelines import guides as gp


def _project(fps: float = 30.0, guides=None) -> KdenliveProject:
    return KdenliveProject(
        profile=ProjectProfile(width=1920, height=1080, fps=fps),
        guides=list(guides or []),
    )


# ---------------------------------------------------------------------------
# Frame / time math
# ---------------------------------------------------------------------------

class TestFrameMath:
    @pytest.mark.parametrize(
        "seconds,fps,frames",
        [
            (0.0, 25.0, 0),
            (1.0, 25.0, 25),
            (2.0, 30.0, 60),
            (1.001, 24.0, 24),   # rounds to nearest frame
            (10.0, 23.976, 240),  # 239.76 -> 240
        ],
    )
    def test_seconds_to_frames(self, seconds, fps, frames):
        assert gp.seconds_to_frames(seconds, fps) == frames

    def test_round_trip_frames_seconds(self):
        assert gp.frames_to_seconds(60, 30.0) == pytest.approx(2.0)

    def test_zero_fps_falls_back(self):
        assert gp.seconds_to_frames(1.0, 0) == int(round(gp.DEFAULT_FPS))

    def test_project_fps_fallback(self):
        proj = _project(fps=0.0)
        assert gp.project_fps(proj) == gp.DEFAULT_FPS


class TestFormatTimestamp:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00"),
            (5.0, "00:05"),
            (65.0, "01:05"),
            (330.0, "05:30"),
            (3600.0, "1:00:00"),
            (3930.0, "1:05:30"),
            (59.9, "00:59"),   # floored, not rounded up
        ],
    )
    def test_format(self, seconds, expected):
        assert gp.format_timestamp(seconds) == expected

    def test_negative_clamps_to_zero(self):
        assert gp.format_timestamp(-3.0) == "00:00"


# ---------------------------------------------------------------------------
# Guide operations
# ---------------------------------------------------------------------------

class TestGuideOps:
    def test_add_guide_is_pure(self):
        proj = _project(fps=30.0)
        new = gp.add_guide(proj, 2.0, "Intro")
        assert len(proj.guides) == 0            # original unchanged
        assert len(new.guides) == 1
        assert new.guides[0].position == 60     # 2s * 30fps
        assert new.guides[0].label == "Intro"

    def test_add_guide_category(self):
        new = gp.add_guide(_project(), 1.0, "Chapter", category="2")
        assert new.guides[0].category == "2"

    def test_list_guides_sorted(self):
        proj = _project(
            fps=30.0,
            guides=[Guide(position=90, label="B"), Guide(position=0, label="A")],
        )
        rows = gp.list_guides(proj)
        assert [r["label"] for r in rows] == ["A", "B"]
        assert rows[0]["timecode"] == "00:00"
        assert rows[1]["at_seconds"] == pytest.approx(3.0)

    def test_remove_by_label(self):
        proj = _project(
            guides=[Guide(position=0, label="Intro"), Guide(position=60, label="Mid")]
        )
        new, removed = gp.remove_guide(proj, "intro")  # case-insensitive
        assert len(removed) == 1
        assert removed[0]["label"] == "Intro"
        assert [g.label for g in new.guides] == ["Mid"]

    def test_remove_by_seconds(self):
        proj = _project(
            fps=30.0,
            guides=[Guide(position=0, label="Intro"), Guide(position=60, label="Mid")],
        )
        new, removed = gp.remove_guide(proj, 2.0)  # 2s -> frame 60
        assert len(removed) == 1
        assert removed[0]["label"] == "Mid"
        assert [g.label for g in new.guides] == ["Intro"]

    def test_remove_no_match(self):
        proj = _project(guides=[Guide(position=0, label="Intro")])
        new, removed = gp.remove_guide(proj, "nope")
        assert removed == []
        assert len(new.guides) == 1

    def test_docproperties_json(self):
        proj = _project(
            fps=30.0,
            guides=[
                Guide(position=60, label="Mid", category="2"),
                Guide(position=0, label="Intro"),
            ],
        )
        data = json.loads(gp.guides_docproperties_json(proj))
        assert data == [
            {"pos": 0, "comment": "Intro", "type": 0},
            {"pos": 60, "comment": "Mid", "type": 2},
        ]


# ---------------------------------------------------------------------------
# Chapter formatting + min-gap merge
# ---------------------------------------------------------------------------

class TestChapters:
    def test_merge_min_gap_drops_close(self):
        chapters = [
            {"time": 0.0, "title": "A"},
            {"time": 5.0, "title": "B"},   # within 10s of A -> dropped
            {"time": 20.0, "title": "C"},
        ]
        merged = gp.merge_min_gap(chapters, 10.0)
        assert [c["title"] for c in merged] == ["A", "C"]

    def test_merge_keeps_first_always(self):
        merged = gp.merge_min_gap([{"time": 3.0, "title": "X"}], 10.0)
        assert merged == [{"time": 3.0, "title": "X"}]

    def test_prepare_inserts_intro_at_zero(self):
        prepared = gp.prepare_chapters([{"time": 30.0, "title": "Setup"}], 10.0)
        assert prepared[0] == {"time": 0.0, "title": "Intro"}
        assert prepared[1]["title"] == "Setup"

    def test_prepare_no_duplicate_intro(self):
        prepared = gp.prepare_chapters(
            [{"time": 0.0, "title": "Start"}, {"time": 40.0, "title": "Next"}], 10.0
        )
        assert [c["title"] for c in prepared] == ["Start", "Next"]

    def test_format_lines(self):
        prepared = [
            {"time": 0.0, "title": "Intro"},
            {"time": 330.0, "title": "Chapter One"},
        ]
        assert gp.format_chapter_lines(prepared) == "00:00 Intro\n05:30 Chapter One"

    def test_first_line_always_zero(self):
        prepared = gp.prepare_chapters([{"time": 45.0, "title": "X"}], 10.0)
        text = gp.format_chapter_lines(prepared)
        assert text.startswith("00:00 ")

    def test_warnings_first_not_zero(self):
        warnings = gp.youtube_chapter_warnings(
            [{"time": 5.0, "title": "A"}, {"time": 20.0, "title": "B"},
             {"time": 40.0, "title": "C"}],
            10.0,
        )
        assert any("00:00" in w for w in warnings)

    def test_warnings_too_few(self):
        warnings = gp.youtube_chapter_warnings(
            [{"time": 0.0, "title": "A"}, {"time": 30.0, "title": "B"}], 10.0
        )
        assert any("three" in w for w in warnings)

    def test_warnings_too_close(self):
        warnings = gp.youtube_chapter_warnings(
            [{"time": 0.0, "title": "A"}, {"time": 3.0, "title": "B"},
             {"time": 30.0, "title": "C"}],
            10.0,
        )
        assert any("apart" in w for w in warnings)

    def test_no_warnings_valid(self):
        warnings = gp.youtube_chapter_warnings(
            [{"time": 0.0, "title": "A"}, {"time": 15.0, "title": "B"},
             {"time": 40.0, "title": "C"}],
            10.0,
        )
        assert warnings == []
