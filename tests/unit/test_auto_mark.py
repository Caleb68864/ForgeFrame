"""Unit tests for auto_mark pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker, MarkerConfig, MarkerRule
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
from workshop_video_brain.edit_mcp.pipelines.marker_rules import default_config

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "transcripts"


def _make_transcript(segments: list[dict]) -> Transcript:
    return Transcript(
        asset_id=UUID("22222222-2222-2222-2222-222222222222"),
        engine="whisper",
        segments=[TranscriptSegment(**s) for s in segments],
    )


def _load_sample_tutorial() -> Transcript:
    data = json.loads((FIXTURES_DIR / "sample_tutorial.json").read_text())
    return Transcript.model_validate(data)


class TestGenerateMarkersTutorial:
    def test_keywords_produce_markers(self):
        transcript = _load_sample_tutorial()
        config = default_config()
        markers = generate_markers(transcript, [], config)
        categories = {str(m.category) for m in markers}
        # Tutorial has materials, steps, cautions, mistakes, chapters — expect these
        assert MarkerCategory.materials_mention.value in categories
        assert MarkerCategory.step_explanation.value in categories
        assert MarkerCategory.important_caution.value in categories
        assert MarkerCategory.mistake_problem.value in categories

    def test_intro_candidate_generated(self):
        transcript = _load_sample_tutorial()
        config = default_config()
        markers = generate_markers(transcript, [], config)
        intro_markers = [m for m in markers if str(m.category) == MarkerCategory.intro_candidate.value]
        assert len(intro_markers) >= 1
        assert intro_markers[0].start_seconds < 30.0

    def test_ending_reveal_generated(self):
        transcript = _load_sample_tutorial()
        config = default_config()
        markers = generate_markers(transcript, [], config)
        ending_markers = [m for m in markers if str(m.category) == MarkerCategory.ending_reveal.value]
        assert len(ending_markers) >= 1

    def test_all_markers_have_required_fields(self):
        transcript = _load_sample_tutorial()
        config = default_config()
        markers = generate_markers(transcript, [], config)
        for m in markers:
            assert m.category is not None
            assert 0.0 <= m.confidence_score <= 1.0
            assert m.source_method != ""
            assert m.reason != ""
            assert m.clip_ref != ""
            assert m.end_seconds >= m.start_seconds


class TestSilenceGaps:
    def test_silence_gaps_produce_dead_air(self):
        transcript = _make_transcript([
            {"start_seconds": 0.5, "end_seconds": 3.0, "text": "Hello there."},
            {"start_seconds": 10.0, "end_seconds": 12.0, "text": "Welcome back."},
        ])
        config = default_config()
        silence_gaps = [(3.5, 9.0)]  # 5.5 seconds — above threshold
        markers = generate_markers(transcript, silence_gaps, config)
        dead_air_markers = [m for m in markers if str(m.category) == MarkerCategory.dead_air.value]
        assert len(dead_air_markers) >= 1
        assert dead_air_markers[0].start_seconds == 3.5
        assert dead_air_markers[0].end_seconds == 9.0

    def test_short_silence_below_threshold_ignored(self):
        transcript = _make_transcript([
            {"start_seconds": 0.5, "end_seconds": 3.0, "text": "Hello."},
        ])
        config = default_config()
        silence_gaps = [(3.1, 4.5)]  # 1.4 seconds — below default 2.0s threshold
        markers = generate_markers(transcript, silence_gaps, config)
        dead_air_markers = [m for m in markers if str(m.category) == MarkerCategory.dead_air.value]
        assert len(dead_air_markers) == 0

    def test_all_silence_transcript_only_dead_air(self):
        """Transcript with no meaningful speech, only silence gaps."""
        transcript = _make_transcript([])  # empty segments
        config = default_config()
        # Gaps are separated by > 3s so they remain distinct after merging
        silence_gaps = [(0.0, 5.0), (10.0, 16.0), (22.0, 28.0)]
        markers = generate_markers(transcript, silence_gaps, config)
        categories = {str(m.category) for m in markers}
        # Only dead_air should appear (no speech → no intro/ending/keywords)
        assert categories == {MarkerCategory.dead_air.value}
        assert len(markers) == 3

    def test_silence_at_threshold_included(self):
        transcript = _make_transcript([
            {"start_seconds": 0.5, "end_seconds": 3.0, "text": "Hello."},
        ])
        config = default_config()
        silence_gaps = [(3.5, 5.5)]  # exactly 2.0 seconds — at threshold
        markers = generate_markers(transcript, silence_gaps, config)
        dead_air_markers = [m for m in markers if str(m.category) == MarkerCategory.dead_air.value]
        assert len(dead_air_markers) == 1


class TestDeterminism:
    def test_same_inputs_produce_same_output(self):
        transcript = _load_sample_tutorial()
        config = default_config()
        silence_gaps = [(27.0, 30.0), (57.5, 60.0)]
        first = generate_markers(transcript, silence_gaps, config)
        second = generate_markers(transcript, silence_gaps, config)
        assert len(first) == len(second)
        for a, b in zip(first, second):
            assert str(a.category) == str(b.category)
            assert a.start_seconds == b.start_seconds
            assert a.end_seconds == b.end_seconds
            assert a.confidence_score == b.confidence_score


class TestEmptyTranscript:
    def test_empty_transcript_no_markers_no_crash(self):
        transcript = _make_transcript([])
        config = default_config()
        markers = generate_markers(transcript, [], config)
        assert markers == []

    def test_empty_transcript_with_silence_only_dead_air(self):
        transcript = _make_transcript([])
        config = default_config()
        silence_gaps = [(0.0, 5.0)]
        markers = generate_markers(transcript, silence_gaps, config)
        assert len(markers) == 1
        assert str(markers[0].category) == MarkerCategory.dead_air.value


class TestMarkerMerging:
    def test_nearby_same_category_markers_merged(self):
        """Two segments with same category keyword within gap → merged into one."""
        config = default_config()
        # Two step_explanation segments within 3s of each other
        transcript = _make_transcript([
            {"start_seconds": 10.0, "end_seconds": 12.0, "text": "First, do this."},
            {"start_seconds": 13.5, "end_seconds": 15.0, "text": "Next, do that."},
        ])
        markers = generate_markers(transcript, [], config)
        step_markers = [m for m in markers if str(m.category) == MarkerCategory.step_explanation.value]
        # Gap between 12.0 and 13.5 = 1.5s < merge_gap (3.0s) → should merge
        assert len(step_markers) == 1
        assert step_markers[0].start_seconds == 10.0
        assert step_markers[0].end_seconds == 15.0

    def test_distant_same_category_not_merged(self):
        """Two segments with same category keyword far apart → not merged."""
        config = default_config()
        transcript = _make_transcript([
            {"start_seconds": 10.0, "end_seconds": 12.0, "text": "First, do this step here."},
            {"start_seconds": 20.0, "end_seconds": 22.0, "text": "Next, do the next step."},
        ])
        markers = generate_markers(transcript, [], config)
        step_markers = [m for m in markers if str(m.category) == MarkerCategory.step_explanation.value]
        # Gap between 12.0 and 20.0 = 8.0s > merge_gap (3.0s) → should NOT merge
        assert len(step_markers) == 2

    def test_different_categories_not_merged(self):
        """Same time range but different categories → not merged."""
        config = default_config()
        transcript = _make_transcript([
            {"start_seconds": 5.0, "end_seconds": 8.0, "text": "You'll need some materials and supplies."},
            {"start_seconds": 9.0, "end_seconds": 11.0, "text": "Be careful and watch out."},
        ])
        markers = generate_markers(transcript, [], config)
        mats = [m for m in markers if str(m.category) == MarkerCategory.materials_mention.value]
        caut = [m for m in markers if str(m.category) == MarkerCategory.important_caution.value]
        assert len(mats) >= 1
        assert len(caut) >= 1


class TestExtraKeywords:
    def test_extra_keywords_generate_markers(self):
        transcript = _make_transcript([
            {"start_seconds": 5.0, "end_seconds": 10.0, "text": "Here we discuss the shoulder strap."},
        ])
        config = default_config()
        markers = generate_markers(transcript, [], config, extra_keywords=["shoulder strap"])
        cats = {str(m.category) for m in markers}
        assert MarkerCategory.chapter_candidate.value in cats

    def test_no_extra_keywords_no_extra_markers(self):
        transcript = _make_transcript([
            {"start_seconds": 5.0, "end_seconds": 10.0, "text": "Plain text with nothing special."},
        ])
        config = default_config()
        markers_no_extra = generate_markers(transcript, [], config)
        markers_with_none = generate_markers(transcript, [], config, extra_keywords=None)
        # Both calls should produce the same result (intro_candidate for speech start)
        assert len(markers_no_extra) == len(markers_with_none)
