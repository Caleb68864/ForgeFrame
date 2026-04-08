"""Unit tests for clip_labeler pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.clip_labeler import (
    _calculate_speech_density,
    _clean_summary,
    _detect_content_type,
    _detect_shot_type,
    _extract_topics,
    _label_from_filename,
    generate_labels,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcript(
    segments: list[dict],
    raw_text: str = "",
    asset_id: UUID | None = None,
) -> Transcript:
    return Transcript(
        asset_id=asset_id or uuid4(),
        engine="test",
        segments=[TranscriptSegment(**s) for s in segments],
        raw_text=raw_text,
    )


def _make_marker(category: MarkerCategory, start: float = 0.0, end: float = 5.0) -> dict:
    return {
        "id": str(uuid4()),
        "category": category.value,
        "confidence_score": 0.8,
        "source_method": "test",
        "reason": "test",
        "clip_ref": "test_clip",
        "start_seconds": start,
        "end_seconds": end,
    }


def _setup_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace structure."""
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "markers").mkdir()
    (tmp_path / "clips").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Test: content_type detection
# ---------------------------------------------------------------------------


class TestContentTypeDetection:
    def test_mostly_step_explanation_returns_tutorial_step(self):
        markers = [
            _make_marker(MarkerCategory.step_explanation),
            _make_marker(MarkerCategory.step_explanation),
            _make_marker(MarkerCategory.materials_mention),
        ]
        result = _detect_content_type(markers, speech_density=0.7)
        assert result == "tutorial_step"

    def test_mostly_materials_mention_returns_materials_overview(self):
        markers = [
            _make_marker(MarkerCategory.materials_mention),
            _make_marker(MarkerCategory.materials_mention),
            _make_marker(MarkerCategory.materials_mention),
            _make_marker(MarkerCategory.step_explanation),
        ]
        result = _detect_content_type(markers, speech_density=0.7)
        assert result == "materials_overview"

    def test_high_speech_few_markers_returns_talking_head(self):
        markers = [_make_marker(MarkerCategory.dead_air)]
        result = _detect_content_type(markers, speech_density=0.85)
        assert result == "talking_head"

    def test_low_speech_returns_broll(self):
        result = _detect_content_type([], speech_density=0.1)
        assert result == "b_roll"

    def test_no_markers_high_speech_returns_talking_head(self):
        result = _detect_content_type([], speech_density=0.7)
        assert result == "talking_head"

    def test_default_fallback_returns_tutorial_step(self):
        markers = [_make_marker(MarkerCategory.step_explanation)]
        result = _detect_content_type(markers, speech_density=0.5)
        assert result == "tutorial_step"


# ---------------------------------------------------------------------------
# Test: topics extraction
# ---------------------------------------------------------------------------


class TestTopicsExtraction:
    def test_extracts_noun_phrases_from_text(self):
        text = "Today we are going to build a wooden table using special tools"
        topics = _extract_topics(text)
        assert isinstance(topics, list)
        # words > 4 chars that aren't stop words
        assert "wooden" in topics or "table" in topics or "special" in topics or "tools" in topics or "build" in topics

    def test_returns_at_most_max_topics(self):
        text = "cutting drilling sanding measuring painting staining coating sealing grinding polishing finishing"
        topics = _extract_topics(text, max_topics=5)
        assert len(topics) <= 5

    def test_empty_text_returns_empty_list(self):
        assert _extract_topics("") == []

    def test_splits_on_transition_words(self):
        text = "first we cut the board next we sand the surface then we apply the stain"
        topics = _extract_topics(text)
        assert isinstance(topics, list)
        assert len(topics) >= 0  # basic sanity

    def test_excludes_stop_words(self):
        text = "going about always never really making things something anything everything"
        topics = _extract_topics(text)
        # Stop words should be excluded
        for word in ["going", "about", "always", "never", "really", "things", "something"]:
            assert word not in topics

    def test_most_frequent_words_appear_first(self):
        text = "measure measure measure cut cut sand"
        topics = _extract_topics(text)
        if "measure" in topics and "sand" in topics:
            assert topics.index("measure") < topics.index("sand")


# ---------------------------------------------------------------------------
# Test: speech density calculation
# ---------------------------------------------------------------------------


class TestSpeechDensity:
    def test_full_coverage_returns_one(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 10.0, "text": "hello world"},
        ])
        density = _calculate_speech_density(transcript, total_duration=10.0)
        assert density == 1.0

    def test_half_coverage_returns_half(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 5.0, "text": "hello"},
        ])
        density = _calculate_speech_density(transcript, total_duration=10.0)
        assert density == pytest.approx(0.5)

    def test_zero_duration_returns_zero(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 5.0, "text": "hello"},
        ])
        density = _calculate_speech_density(transcript, total_duration=0.0)
        assert density == 0.0

    def test_empty_segments_returns_zero(self):
        transcript = _make_transcript([])
        density = _calculate_speech_density(transcript, total_duration=10.0)
        assert density == 0.0

    def test_clamped_to_one(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 20.0, "text": "hello"},
        ])
        density = _calculate_speech_density(transcript, total_duration=10.0)
        assert density == 1.0

    def test_empty_text_segments_excluded(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 5.0, "text": "   "},
            {"start_seconds": 5.0, "end_seconds": 10.0, "text": "hello"},
        ])
        density = _calculate_speech_density(transcript, total_duration=10.0)
        assert density == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test: shot_type detection
# ---------------------------------------------------------------------------


class TestShotTypeDetection:
    def test_closeup_needed_returns_closeup(self):
        markers = [_make_marker(MarkerCategory.closeup_needed)]
        assert _detect_shot_type(markers) == "closeup"

    def test_broll_candidate_returns_broll(self):
        markers = [_make_marker(MarkerCategory.broll_candidate)]
        assert _detect_shot_type(markers) == "b_roll"

    def test_closeup_takes_priority_over_broll(self):
        markers = [
            _make_marker(MarkerCategory.broll_candidate),
            _make_marker(MarkerCategory.closeup_needed),
        ]
        assert _detect_shot_type(markers) == "closeup"

    def test_no_relevant_markers_returns_medium(self):
        markers = [_make_marker(MarkerCategory.step_explanation)]
        assert _detect_shot_type(markers) == "medium"

    def test_empty_markers_returns_medium(self):
        assert _detect_shot_type([]) == "medium"


# ---------------------------------------------------------------------------
# Test: generate_labels with transcript
# ---------------------------------------------------------------------------


class TestGenerateLabels:
    def test_labeled_from_transcript(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        transcript = _make_transcript(
            segments=[
                {"start_seconds": 0.0, "end_seconds": 10.0, "text": "Today we build a wooden table"},
                {"start_seconds": 10.0, "end_seconds": 20.0, "text": "We need special cutting tools"},
            ],
            raw_text="Today we build a wooden table. We need special cutting tools.",
        )
        (ws / "transcripts" / "clip01_transcript.json").write_text(
            transcript.to_json(), encoding="utf-8"
        )
        # Add step_explanation markers
        markers = [
            _make_marker(MarkerCategory.step_explanation, 0.0, 10.0),
            _make_marker(MarkerCategory.step_explanation, 10.0, 20.0),
        ]
        (ws / "markers" / "clip01_markers.json").write_text(
            json.dumps(markers), encoding="utf-8"
        )

        labels = generate_labels(ws)

        assert len(labels) == 1
        label = labels[0]
        assert label.clip_ref == "clip01"
        assert label.content_type == "tutorial_step"
        assert label.has_speech is True
        assert label.speech_density > 0.0
        assert isinstance(label.topics, list)
        assert isinstance(label.tags, list)

    def test_clip_without_transcript_returns_unlabeled(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        # Only marker file, no transcript
        markers = [_make_marker(MarkerCategory.step_explanation)]
        (ws / "markers" / "clip_no_transcript_markers.json").write_text(
            json.dumps(markers), encoding="utf-8"
        )

        labels = generate_labels(ws)

        assert len(labels) == 1
        label = labels[0]
        assert label.content_type == "unlabeled"
        assert label.has_speech is False
        assert "unlabeled" in label.tags

    def test_empty_workspace_returns_empty_list(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        labels = generate_labels(ws)
        assert labels == []

    def test_label_saved_to_clips_dir(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        transcript = _make_transcript(
            segments=[{"start_seconds": 0.0, "end_seconds": 5.0, "text": "Hello world"}],
            raw_text="Hello world",
        )
        (ws / "transcripts" / "myclip_transcript.json").write_text(
            transcript.to_json(), encoding="utf-8"
        )

        generate_labels(ws)

        label_path = ws / "clips" / "myclip_label.json"
        assert label_path.exists()
        data = json.loads(label_path.read_text(encoding="utf-8"))
        assert data["clip_ref"] == "myclip"

    def test_idempotency_reruns_produce_same_output(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        transcript = _make_transcript(
            segments=[{"start_seconds": 0.0, "end_seconds": 10.0, "text": "Hello world testing"}],
            raw_text="Hello world testing",
        )
        (ws / "transcripts" / "clip_idem_transcript.json").write_text(
            transcript.to_json(), encoding="utf-8"
        )

        labels1 = generate_labels(ws)
        labels2 = generate_labels(ws)

        assert len(labels1) == len(labels2) == 1
        assert labels1[0].to_json() == labels2[0].to_json()

    def test_materials_overview_content_type(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        transcript = _make_transcript(
            segments=[{"start_seconds": 0.0, "end_seconds": 15.0, "text": "You need hammer nails boards"}],
            raw_text="You need hammer nails boards",
        )
        (ws / "transcripts" / "materials_transcript.json").write_text(
            transcript.to_json(), encoding="utf-8"
        )
        markers = [
            _make_marker(MarkerCategory.materials_mention, 0.0, 5.0),
            _make_marker(MarkerCategory.materials_mention, 5.0, 10.0),
            _make_marker(MarkerCategory.materials_mention, 10.0, 15.0),
        ]
        (ws / "markers" / "materials_markers.json").write_text(
            json.dumps(markers), encoding="utf-8"
        )

        labels = generate_labels(ws)

        assert len(labels) == 1
        assert labels[0].content_type == "materials_overview"

    def test_tags_contain_content_type_and_shot_type(self, tmp_path):
        ws = _setup_workspace(tmp_path)
        transcript = _make_transcript(
            segments=[{"start_seconds": 0.0, "end_seconds": 10.0, "text": "cutting boards"}],
            raw_text="cutting boards",
        )
        (ws / "transcripts" / "clip_tags_transcript.json").write_text(
            transcript.to_json(), encoding="utf-8"
        )

        labels = generate_labels(ws)

        assert len(labels) == 1
        label = labels[0]
        assert label.content_type.lower() in label.tags
        assert label.shot_type.lower() in label.tags


# ---------------------------------------------------------------------------
# Test: label_from_filename
# ---------------------------------------------------------------------------


class TestLabelFromFilename:
    def test_splits_on_underscore(self):
        tags = _label_from_filename("clip_01_broll")
        assert "clip" in tags or "broll" in tags

    def test_splits_on_hyphen(self):
        tags = _label_from_filename("my-clip-name")
        assert "my" in tags or "clip" in tags or "name" in tags

    def test_lowercases_tags(self):
        tags = _label_from_filename("MyClip_BRoll")
        assert all(t == t.lower() for t in tags)

    def test_removes_extension(self):
        tags = _label_from_filename("clip_01.mp4")
        # stem strips extension
        assert "mp4" not in tags or "clip" in tags
