"""Unit tests for the Title Card Generator pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.kdenlive import KdenliveProject, ProjectProfile
from workshop_video_brain.core.models.title_cards import TitleCard
from workshop_video_brain.edit_mcp.pipelines.title_cards import (
    _clean_label,
    apply_title_cards_to_project,
    generate_title_cards,
    save_title_cards,
    title_cards_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_marker_dict(
    category: str = "chapter_candidate",
    start_seconds: float = 10.0,
    suggested_label: str = "chapter_candidate: Introduction",
    reason: str = "Keyword match",
) -> dict:
    return {
        "id": str(uuid4()),
        "category": category,
        "confidence_score": 0.8,
        "source_method": "keyword_rule",
        "reason": reason,
        "clip_ref": "clip01",
        "start_seconds": start_seconds,
        "end_seconds": start_seconds + 5.0,
        "suggested_label": suggested_label,
    }


def _write_markers(markers_dir: Path, stem: str, markers: list[dict]) -> None:
    markers_dir.mkdir(parents=True, exist_ok=True)
    path = markers_dir / f"{stem}_markers.json"
    path.write_text(json.dumps(markers), encoding="utf-8")


def _make_project(fps: float = 25.0) -> KdenliveProject:
    return KdenliveProject(
        profile=ProjectProfile(fps=fps),
    )


# ---------------------------------------------------------------------------
# TitleCard model
# ---------------------------------------------------------------------------


class TestTitleCardModel:
    def test_defaults(self):
        card = TitleCard(chapter_title="Intro", timestamp_seconds=0.0)
        assert card.subtitle == ""
        assert card.duration_seconds == 3.0
        assert card.style == "standard"

    def test_custom_fields(self):
        card = TitleCard(
            chapter_title="Setup",
            timestamp_seconds=15.5,
            subtitle="Getting started",
            duration_seconds=5.0,
            style="bold",
        )
        assert card.chapter_title == "Setup"
        assert card.timestamp_seconds == 15.5
        assert card.subtitle == "Getting started"
        assert card.duration_seconds == 5.0
        assert card.style == "bold"

    def test_serializable(self):
        card = TitleCard(chapter_title="Test", timestamp_seconds=0.0)
        data = json.loads(card.to_json())
        assert data["chapter_title"] == "Test"
        assert data["timestamp_seconds"] == 0.0


# ---------------------------------------------------------------------------
# Label cleaning
# ---------------------------------------------------------------------------


class TestCleanLabel:
    def test_removes_chapter_candidate_prefix(self):
        assert _clean_label("chapter_candidate: Introduction") == "Introduction"

    def test_removes_prefix_case_insensitive(self):
        assert _clean_label("Chapter_Candidate: My Chapter") == "My Chapter"

    def test_removes_confidence_score(self):
        result = _clean_label("Some topic [confidence: 0.9]")
        assert "confidence" not in result
        assert "0.9" not in result

    def test_removes_generic_brackets(self):
        result = _clean_label("My Chapter [extra info]")
        assert "[extra info]" not in result
        assert "My Chapter" in result

    def test_strips_whitespace(self):
        result = _clean_label("  chapter_candidate:   Clean Title  ")
        assert result == "Clean Title"

    def test_no_prefix_passthrough(self):
        assert _clean_label("Plain Title") == "Plain Title"


# ---------------------------------------------------------------------------
# generate_title_cards
# ---------------------------------------------------------------------------


class TestGenerateTitleCards:
    def test_empty_markers_dir_returns_intro_card(self, tmp_path):
        cards = generate_title_cards(tmp_path)
        assert len(cards) == 1
        assert cards[0].chapter_title == "Intro"
        assert cards[0].timestamp_seconds == 0.0

    def test_missing_markers_dir_returns_intro_card(self, tmp_path):
        # No markers/ dir at all
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        cards = generate_title_cards(workspace)
        assert len(cards) == 1
        assert cards[0].chapter_title == "Intro"

    def test_chapter_markers_produce_cards(self, tmp_path):
        markers_dir = tmp_path / "markers"
        _write_markers(markers_dir, "clip01", [
            _make_marker_dict(start_seconds=30.0, suggested_label="chapter_candidate: Cutting"),
            _make_marker_dict(start_seconds=60.0, suggested_label="chapter_candidate: Assembly"),
        ])

        cards = generate_title_cards(tmp_path)

        # Should include Intro + 2 chapters
        assert len(cards) == 3
        titles = [c.chapter_title for c in cards]
        assert "Intro" in titles
        assert "Cutting" in titles
        assert "Assembly" in titles

    def test_chapter_at_zero_no_duplicate_intro(self, tmp_path):
        markers_dir = tmp_path / "markers"
        _write_markers(markers_dir, "clip01", [
            _make_marker_dict(start_seconds=0.0, suggested_label="chapter_candidate: Opening"),
        ])

        cards = generate_title_cards(tmp_path)

        # Should not have duplicate at 0.0
        zero_cards = [c for c in cards if c.timestamp_seconds == 0.0]
        assert len(zero_cards) == 1
        # Intro should not be inserted
        titles = [c.chapter_title for c in cards]
        assert "Intro" not in titles
        assert "Opening" in titles

    def test_cards_sorted_by_timestamp(self, tmp_path):
        markers_dir = tmp_path / "markers"
        _write_markers(markers_dir, "clip01", [
            _make_marker_dict(start_seconds=90.0, suggested_label="chapter_candidate: Third"),
            _make_marker_dict(start_seconds=30.0, suggested_label="chapter_candidate: First"),
            _make_marker_dict(start_seconds=60.0, suggested_label="chapter_candidate: Second"),
        ])

        cards = generate_title_cards(tmp_path)

        timestamps = [c.timestamp_seconds for c in cards]
        assert timestamps == sorted(timestamps)

    def test_non_chapter_markers_ignored(self, tmp_path):
        markers_dir = tmp_path / "markers"
        _write_markers(markers_dir, "clip01", [
            _make_marker_dict(category="dead_air", start_seconds=10.0),
            _make_marker_dict(category="mistake_problem", start_seconds=20.0),
        ])

        cards = generate_title_cards(tmp_path)

        # Only the default Intro card
        assert len(cards) == 1
        assert cards[0].chapter_title == "Intro"

    def test_label_cleaning_applied(self, tmp_path):
        markers_dir = tmp_path / "markers"
        _write_markers(markers_dir, "clip01", [
            _make_marker_dict(
                start_seconds=15.0,
                suggested_label="chapter_candidate: Setup [confidence: 0.85]",
            ),
        ])

        cards = generate_title_cards(tmp_path)

        chapter_cards = [c for c in cards if c.chapter_title != "Intro"]
        assert len(chapter_cards) == 1
        assert chapter_cards[0].chapter_title == "Setup"


# ---------------------------------------------------------------------------
# title_cards_to_json
# ---------------------------------------------------------------------------


class TestTitleCardsToJson:
    def test_returns_valid_json_array(self):
        cards = [
            TitleCard(chapter_title="Intro", timestamp_seconds=0.0),
            TitleCard(chapter_title="Setup", timestamp_seconds=30.0),
        ]
        result = title_cards_to_json(cards)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_empty_list_returns_empty_array(self):
        result = title_cards_to_json([])
        assert json.loads(result) == []

    def test_fields_preserved(self):
        card = TitleCard(
            chapter_title="Test",
            timestamp_seconds=5.5,
            subtitle="sub",
            duration_seconds=4.0,
            style="bold",
        )
        parsed = json.loads(title_cards_to_json([card]))
        assert parsed[0]["chapter_title"] == "Test"
        assert parsed[0]["timestamp_seconds"] == 5.5
        assert parsed[0]["subtitle"] == "sub"
        assert parsed[0]["duration_seconds"] == 4.0
        assert parsed[0]["style"] == "bold"


# ---------------------------------------------------------------------------
# apply_title_cards_to_project
# ---------------------------------------------------------------------------


class TestApplyTitleCardsToProject:
    def test_guides_added_to_project(self):
        project = _make_project(fps=25.0)
        cards = [
            TitleCard(chapter_title="Intro", timestamp_seconds=0.0),
            TitleCard(chapter_title="Setup", timestamp_seconds=10.0),
        ]
        result = apply_title_cards_to_project(project, cards)
        assert len(result.guides) == 2

    def test_guide_labels_prefixed_with_title(self):
        project = _make_project(fps=25.0)
        cards = [TitleCard(chapter_title="My Chapter", timestamp_seconds=0.0)]
        result = apply_title_cards_to_project(project, cards)
        assert result.guides[0].label == "TITLE: My Chapter"

    def test_guide_position_calculated_from_fps(self):
        project = _make_project(fps=30.0)
        cards = [TitleCard(chapter_title="Chapter", timestamp_seconds=2.0)]
        result = apply_title_cards_to_project(project, cards)
        # 2.0s * 30fps = 60 frames
        assert result.guides[0].position == 60

    def test_does_not_mutate_original(self):
        project = _make_project(fps=25.0)
        original_guide_count = len(project.guides)
        cards = [TitleCard(chapter_title="Intro", timestamp_seconds=0.0)]
        apply_title_cards_to_project(project, cards)
        assert len(project.guides) == original_guide_count

    def test_existing_guides_preserved(self):
        from workshop_video_brain.core.models.kdenlive import Guide
        project = _make_project(fps=25.0)
        project = project.model_copy(
            update={"guides": [Guide(position=0, label="Existing")]}
        )
        cards = [TitleCard(chapter_title="New", timestamp_seconds=5.0)]
        result = apply_title_cards_to_project(project, cards)
        labels = [g.label for g in result.guides]
        assert "Existing" in labels
        assert "TITLE: New" in labels


# ---------------------------------------------------------------------------
# save_title_cards
# ---------------------------------------------------------------------------


class TestSaveTitleCards:
    def test_file_written_to_reports_dir(self, tmp_path):
        cards = [TitleCard(chapter_title="Intro", timestamp_seconds=0.0)]
        out_path = save_title_cards(cards, tmp_path)
        assert out_path.exists()
        assert out_path == tmp_path / "reports" / "title_cards.json"

    def test_reports_dir_created_if_missing(self, tmp_path):
        workspace = tmp_path / "new_workspace"
        workspace.mkdir()
        cards = [TitleCard(chapter_title="Intro", timestamp_seconds=0.0)]
        out_path = save_title_cards(cards, workspace)
        assert out_path.exists()

    def test_saved_content_is_valid_json(self, tmp_path):
        cards = [
            TitleCard(chapter_title="Intro", timestamp_seconds=0.0),
            TitleCard(chapter_title="Setup", timestamp_seconds=20.0),
        ]
        out_path = save_title_cards(cards, tmp_path)
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2

    def test_returns_path(self, tmp_path):
        cards = []
        result = save_title_cards(cards, tmp_path)
        assert isinstance(result, Path)
