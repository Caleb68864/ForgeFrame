"""Unit tests for the B-Roll Whisperer feature.

Covers:
- detect_broll_opportunities: one test per category, edge cases
- format_broll_suggestions: markdown structure checks
- extract_and_format skill helper
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcript(segments: list[dict], asset_id: str | None = None) -> dict:
    """Build a transcript dict suitable for JSON serialisation."""
    return {
        "id": str(uuid.uuid4()),
        "asset_id": asset_id or str(uuid.uuid4()),
        "engine": "test",
        "model": "test",
        "language": "en",
        "segments": segments,
        "raw_text": " ".join(s["text"] for s in segments),
        "created_at": "2024-01-01T00:00:00",
    }


def _make_segment(start: float, end: float, text: str) -> dict:
    return {
        "start_seconds": start,
        "end_seconds": end,
        "text": text,
        "confidence": 1.0,
        "words": [],
    }


def _build_transcript(segments: list[dict]):
    """Return a Transcript model object from a list of segment dicts."""
    from workshop_video_brain.core.models.transcript import Transcript

    data = _make_transcript(segments)
    return Transcript.from_json(json.dumps(data))


def _write_transcript(tmp_path: Path, name: str, segments: list[dict]) -> Path:
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    data = _make_transcript(segments)
    out = transcripts_dir / f"{name}_transcript.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# detect_broll_opportunities — per-category tests
# ---------------------------------------------------------------------------


class TestDetectBrollOpportunitiesProcessShot:
    def test_process_shot_sew(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Now I'm going to sew along the edge."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "process_shot" in categories

    def test_process_shot_cut(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(5.0, 10.0, "Use the rotary cutter to cut the fabric."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "process_shot" in categories

    def test_process_shot_iron(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(10.0, 15.0, "Iron the seam flat before moving on."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "process_shot" in categories


class TestDetectBrollOpportunitiesMaterialCloseup:
    def test_material_closeup_fabric(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 4.0, "I'm using a Cordura fabric for the outer shell."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "material_closeup" in categories

    def test_material_closeup_thread(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 4.0, "Thread the needle with bonded nylon thread."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "material_closeup" in categories

    def test_material_closeup_dyneema(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 4.0, "This bag uses X-Pac and Dyneema for the body."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "material_closeup" in categories


class TestDetectBrollOpportunitiesToolInUse:
    def test_tool_in_use_scissors(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Grab your scissors and trim the excess."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "tool_in_use" in categories

    def test_tool_in_use_sewing_machine(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Set up your sewing machine with a size 16 needle."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "tool_in_use" in categories

    def test_tool_in_use_awl(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Use an awl to punch the hole through all layers."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "tool_in_use" in categories


class TestDetectBrollOpportunitiesResultReveal:
    def test_result_reveal_finished(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(60.0, 65.0, "The pocket is finished and it looks great."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "result_reveal" in categories

    def test_result_reveal_heres_what(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(120.0, 126.0, "Here's what it looks like when it's done."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "result_reveal" in categories

    def test_result_reveal_turned_out(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(90.0, 95.0, "It turned out really clean on the inside too."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "result_reveal" in categories


class TestDetectBrollOpportunitiesMeasurementShot:
    def test_measurement_shot_inches(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Cut the strap to 24 inches."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "measurement_shot" in categories

    def test_measurement_shot_cm(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Leave a 1.5 cm seam allowance along the edge."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "measurement_shot" in categories

    def test_measurement_shot_measure_verb(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Use the ruler to measure and mark the centre line."),
        ])
        results = detect_broll_opportunities(transcript)
        categories = [r["category"] for r in results]
        assert "measurement_shot" in categories


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestDetectBrollOpportunitiesEdgeCases:
    def test_empty_transcript_returns_empty_list(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([])
        results = detect_broll_opportunities(transcript)
        assert results == []

    def test_no_visual_descriptions_returns_empty_list(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Hello everyone and welcome back to the channel."),
            _make_segment(5.0, 10.0, "Today we are going to talk about backpacks."),
        ])
        results = detect_broll_opportunities(transcript)
        assert results == []

    def test_mixed_transcript_multiple_categories(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        segments = [
            _make_segment(0.0, 5.0, "Hello and welcome."),
            _make_segment(5.0, 10.0, "First, cut the Cordura fabric to size."),
            _make_segment(10.0, 15.0, "Use scissors to trim the corners."),
            _make_segment(15.0, 20.0, "Measure 3 inches from the edge and mark it."),
            _make_segment(20.0, 25.0, "The finished panel looks like this."),
        ]
        transcript = _build_transcript(segments)
        results = detect_broll_opportunities(transcript)
        categories_found = {r["category"] for r in results}
        # Should detect at least process, material, tool, measurement, result
        assert len(categories_found) >= 4

    def test_suggestion_has_required_keys(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Glue the layers together carefully."),
        ])
        results = detect_broll_opportunities(transcript)
        assert len(results) >= 1
        s = results[0]
        for key in ("timestamp", "end_timestamp", "category", "description", "context", "confidence"):
            assert key in s, f"Missing key: {key}"

    def test_timestamp_matches_segment(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(42.5, 47.0, "Press the seam with the iron."),
        ])
        results = detect_broll_opportunities(transcript)
        process_hits = [r for r in results if r["category"] == "process_shot"]
        assert process_hits
        assert process_hits[0]["timestamp"] == 42.5
        assert process_hits[0]["end_timestamp"] == 47.0

    def test_description_contains_show(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            detect_broll_opportunities,
        )

        transcript = _build_transcript([
            _make_segment(0.0, 5.0, "Stitch along the guide line."),
        ])
        results = detect_broll_opportunities(transcript)
        process_hits = [r for r in results if r["category"] == "process_shot"]
        assert process_hits
        assert process_hits[0]["description"].startswith("Show ")


# ---------------------------------------------------------------------------
# format_broll_suggestions
# ---------------------------------------------------------------------------


class TestFormatBrollSuggestions:
    def test_empty_suggestions_returns_valid_markdown(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            format_broll_suggestions,
        )

        result = format_broll_suggestions([])
        assert isinstance(result, str)
        assert result.startswith("#")
        assert "No B-roll opportunities" in result

    def test_non_empty_starts_with_heading(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            format_broll_suggestions,
        )

        suggestions = [
            {
                "timestamp": 5.0,
                "end_timestamp": 10.0,
                "category": "process_shot",
                "description": "Show Process Shot: Cut the fabric.",
                "context": "Cut the fabric.",
                "confidence": 0.8,
            }
        ]
        result = format_broll_suggestions(suggestions)
        assert result.startswith("# B-Roll Suggestions")

    def test_contains_category_heading(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            format_broll_suggestions,
        )

        suggestions = [
            {
                "timestamp": 5.0,
                "end_timestamp": 10.0,
                "category": "result_reveal",
                "description": "Show Result Reveal: It's finished.",
                "context": "It's finished.",
                "confidence": 0.9,
            }
        ]
        result = format_broll_suggestions(suggestions)
        assert "## Result Reveal" in result

    def test_contains_timestamp(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            format_broll_suggestions,
        )

        suggestions = [
            {
                "timestamp": 65.0,  # 1:05
                "end_timestamp": 70.0,  # 1:10
                "category": "tool_in_use",
                "description": "Show Tool in Use: Use scissors.",
                "context": "Use scissors.",
                "confidence": 0.85,
            }
        ]
        result = format_broll_suggestions(suggestions)
        assert "1:05" in result
        assert "1:10" in result

    def test_total_count_in_output(self):
        from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
            format_broll_suggestions,
        )

        suggestions = [
            {
                "timestamp": 0.0,
                "end_timestamp": 5.0,
                "category": "process_shot",
                "description": "Show Process Shot: Sew.",
                "context": "Sew.",
                "confidence": 0.8,
            },
            {
                "timestamp": 10.0,
                "end_timestamp": 15.0,
                "category": "material_closeup",
                "description": "Show Material Close-up: Fabric.",
                "context": "Fabric.",
                "confidence": 0.75,
            },
        ]
        result = format_broll_suggestions(suggestions)
        assert "2" in result  # total count appears somewhere


# ---------------------------------------------------------------------------
# extract_and_format skill helper
# ---------------------------------------------------------------------------


class TestExtractAndFormat:
    def test_no_transcripts_returns_empty_suggestions(self, tmp_path):
        from workshop_video_brain.production_brain.skills.broll import extract_and_format

        markdown, suggestions = extract_and_format(tmp_path)
        assert suggestions == []
        assert isinstance(markdown, str)

    def test_transcript_with_suggestions(self, tmp_path):
        from workshop_video_brain.production_brain.skills.broll import extract_and_format

        _write_transcript(tmp_path, "clip01", [
            _make_segment(0.0, 5.0, "Cut the Cordura to size with scissors."),
            _make_segment(5.0, 10.0, "Measure 15 cm from the edge."),
            _make_segment(10.0, 15.0, "The finished bag looks great."),
        ])

        markdown, suggestions = extract_and_format(tmp_path)
        assert len(suggestions) > 0
        assert isinstance(markdown, str)
        assert "# B-Roll Suggestions" in markdown

    def test_returns_tuple_of_correct_types(self, tmp_path):
        from workshop_video_brain.production_brain.skills.broll import extract_and_format

        _write_transcript(tmp_path, "clip01", [
            _make_segment(0.0, 5.0, "Press the seam flat with the iron."),
        ])
        result = extract_and_format(tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 2
        markdown, suggestions = result
        assert isinstance(markdown, str)
        assert isinstance(suggestions, list)
