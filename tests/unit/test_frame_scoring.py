"""Unit tests for the local frame-quality scorer (SS-07)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    FrameVisualMetrics,
    ResearchConfig,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research import scoring
from workshop_video_brain.edit_mcp.pipelines.visual_research.scoring import (
    MODE_PROFILES,
    FrameScorer,
)

_FFMPEG_TIMEOUT = 60


def _run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT)
    assert result.returncode == 0, result.stderr


def _make_candidate(image_path: Path, timestamp: float = 0.0) -> FrameCandidate:
    return FrameCandidate(
        source_id=uuid4(),
        timestamp_seconds=timestamp,
        image_path=str(image_path),
        width=64,
        height=64,
    )


@pytest.fixture
def black_frame(tmp_path: Path) -> Path:
    out = tmp_path / "black.png"
    _run_ffmpeg(
        ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-frames:v", "1", str(out)]
    )
    return out


@pytest.fixture
def sharp_frame(tmp_path: Path) -> Path:
    out = tmp_path / "sharp.png"
    _run_ffmpeg(
        ["-f", "lavfi", "-i", "testsrc=size=128x128:rate=1", "-frames:v", "1", str(out)]
    )
    return out


@pytest.fixture
def blurred_frame(tmp_path: Path, sharp_frame: Path) -> Path:
    out = tmp_path / "blurred.png"
    _run_ffmpeg(["-i", str(sharp_frame), "-vf", "gblur=sigma=12", "-frames:v", "1", str(out)])
    return out


# --- [STRUCTURAL] -----------------------------------------------------------


def test_frame_scorer_has_score_and_rank():
    scorer = FrameScorer()
    assert hasattr(scorer, "score")
    assert hasattr(scorer, "rank")


def test_score_returns_frame_visual_metrics(black_frame: Path):
    scorer = FrameScorer()
    config = ResearchConfig()
    candidate = _make_candidate(black_frame)

    metrics = scorer.score(candidate, config)

    assert isinstance(metrics, FrameVisualMetrics)


def test_rank_honors_mode_profiles_and_weights(sharp_frame: Path, blurred_frame: Path):
    scorer = FrameScorer()
    config = ResearchConfig()
    candidates = [_make_candidate(blurred_frame, 0.0), _make_candidate(sharp_frame, 1.0)]

    ranked_default = scorer.rank(candidates, config, mode="software_ui")
    assert {c.image_path for c in ranked_default} <= {
        str(sharp_frame),
        str(blurred_frame),
    }

    # An unknown mode falls back to the default profile rather than raising.
    ranked_unknown_mode = scorer.rank(candidates, config, mode="not_a_real_mode")
    assert len(ranked_unknown_mode) == len(ranked_default)

    # Overriding weights to ignore sharpness entirely should not raise and
    # should still return every candidate that passes the quality gate.
    ranked_custom_weights = scorer.rank(
        candidates, config, mode="software_ui", weights={"sharpness": 0.0, "brightness": 1.0}
    )
    assert len(ranked_custom_weights) == len(ranked_default)


def test_mode_profiles_cover_required_modes():
    assert set(MODE_PROFILES) >= {"software_ui", "slide_deck", "physical_demo"}


# --- [BEHAVIORAL] ------------------------------------------------------------


def test_near_black_image_scores_low_brightness_and_is_rejected(black_frame: Path):
    scorer = FrameScorer()
    config = ResearchConfig()
    config.quality.min_brightness = 0.1
    candidate = _make_candidate(black_frame)

    metrics = scorer.score(candidate, config)

    assert metrics.brightness is not None
    assert metrics.brightness < 0.1
    assert scorer.passes_quality_gate(metrics, config) is False

    ranked = scorer.rank([candidate], config)
    assert candidate not in ranked


def test_sharp_image_scores_higher_sharpness_than_blurred_copy(
    sharp_frame: Path, blurred_frame: Path
):
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")

    scorer = FrameScorer()
    config = ResearchConfig()
    sharp_candidate = _make_candidate(sharp_frame, 0.0)
    blurred_candidate = _make_candidate(blurred_frame, 1.0)

    sharp_metrics = scorer.score(sharp_candidate, config)
    blurred_metrics = scorer.score(blurred_candidate, config)

    assert sharp_metrics.sharpness is not None
    assert blurred_metrics.sharpness is not None
    assert sharp_metrics.sharpness > blurred_metrics.sharpness


# --- guarded numpy/Pillow capability check -----------------------------------


def test_pixel_metrics_absent_leaves_fields_none_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, sharp_frame: Path
):
    monkeypatch.setattr(scoring, "_pixel_metrics_available", lambda: False)
    scorer = FrameScorer()
    config = ResearchConfig()
    candidate = _make_candidate(sharp_frame)

    metrics = scorer.score(candidate, config)

    assert metrics.sharpness is None
    assert metrics.entropy is None
    assert "text_density" not in candidate.metadata


def test_pixel_metrics_present_populates_sharpness_and_entropy(
    monkeypatch: pytest.MonkeyPatch, sharp_frame: Path
):
    monkeypatch.setattr(scoring, "_pixel_metrics_available", lambda: True)
    monkeypatch.setattr(
        scoring,
        "_compute_pixel_metrics",
        lambda path: {"sharpness": 42.0, "entropy": 5.5, "text_density": 0.3},
    )
    scorer = FrameScorer()
    config = ResearchConfig()
    candidate = _make_candidate(sharp_frame)

    metrics = scorer.score(candidate, config)

    assert metrics.sharpness == 42.0
    assert metrics.entropy == 5.5
    assert candidate.metadata["text_density"] == 0.3


def test_score_does_not_raise_when_image_missing(tmp_path: Path):
    scorer = FrameScorer()
    config = ResearchConfig()
    candidate = _make_candidate(tmp_path / "does_not_exist.png")

    metrics = scorer.score(candidate, config)

    assert isinstance(metrics, FrameVisualMetrics)
    assert metrics.brightness is None
