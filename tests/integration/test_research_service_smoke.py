"""Integration smoke tests for the visual-research service orchestrator."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.core.models.visual_research import ResearchConfig
from workshop_video_brain.edit_mcp.pipelines.visual_research import service as service_mod
from workshop_video_brain.edit_mcp.pipelines.visual_research.service import research_video

FIXTURE = Path(__file__).parent.parent / "fixtures" / "media_generated" / "greenscreen_reporter_720.mp4"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "source.mp4"
    shutil.copy2(FIXTURE, dest)
    return dest


def _transcript_with_match() -> Transcript:
    return Transcript(
        asset_id=__import__("uuid").uuid4(),
        segments=[
            TranscriptSegment(start_seconds=1.0, end_seconds=4.0, text="the reporter walks on set"),
            TranscriptSegment(start_seconds=9.0, end_seconds=12.0, text="a drone shot of the studio"),
        ],
    )


def test_research_video_end_to_end_produces_manifest_and_package(tmp_path):
    video_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "research_pkg"

    manifest = research_video(
        video_path,
        transcript=_transcript_with_match(),
        query="drone",
        output_dir=output_dir,
    )

    assert len(manifest.regions) >= 1
    assert len(manifest.captures) >= 1
    assert sum(len(c.candidates) for c in manifest.captures) >= 1

    assert output_dir.exists()
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["manifest_version"] == "1.0"
    assert len(payload["captures"]) >= 1

    evidence_path = (
        Path(__file__).parent / "ss10-integration-evidence.md"
    )
    assert evidence_path.exists()


def test_research_video_records_partial_manifest_on_region_error(tmp_path, monkeypatch):
    video_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "research_pkg"

    call_count = {"n": 0}
    real_generate_candidates = service_mod.generate_candidates

    def _flaky_generate_candidates(video_path_arg, region, source, config):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated extraction failure")
        return real_generate_candidates(video_path_arg, region, source, config)

    monkeypatch.setattr(service_mod, "generate_candidates", _flaky_generate_candidates)

    manifest = research_video(
        video_path,
        transcript=_transcript_with_match(),
        topics=["reporter", "drone"],
        output_dir=output_dir,
    )

    assert len(manifest.errors) == 1
    assert "region_id" in manifest.errors[0]
    assert "simulated extraction failure" in manifest.errors[0]["error"]
    # The healthy region still produced a capture -- partial manifest, not an abort.
    assert len(manifest.captures) >= 1


def test_research_video_without_transcript_or_range_respects_candidate_ceiling(tmp_path):
    video_path = _copy_fixture(tmp_path)
    output_dir = tmp_path / "research_pkg"

    config = ResearchConfig()
    config.candidate_generation.max_candidates_per_region = 3
    config.windowing.maximum_region_seconds = 5.0

    manifest = research_video(
        video_path,
        config=config,
        output_dir=output_dir,
    )

    assert len(manifest.regions) == 1
    assert manifest.regions[0].source_method == "uniform_sampling"
    total_candidates = sum(len(c.candidates) for c in manifest.captures)
    assert total_candidates <= config.candidate_generation.max_candidates_per_region
