"""Integration smoke tests for the research/frame/scenes/transcript CLI commands."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from workshop_video_brain.app.cli import main

FIXTURE = Path(__file__).parent.parent / "fixtures" / "media_generated" / "greenscreen_reporter_720.mp4"
TRANSCRIPT_FIXTURE = Path(__file__).parent.parent / "fixtures" / "transcripts" / "sample.json"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _copy_video(tmp_path: Path) -> Path:
    dest = tmp_path / "source.mp4"
    shutil.copy2(FIXTURE, dest)
    return dest


class TestResearchCommand:
    def test_research_end_to_end_json(self, runner: CliRunner, tmp_path: Path):
        video_path = _copy_video(tmp_path)
        output_dir = tmp_path / "research_pkg"

        result = runner.invoke(
            main,
            [
                "research",
                str(video_path),
                "--transcript", str(TRANSCRIPT_FIXTURE),
                "--query", "reporter",
                "--output", str(output_dir),
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "source" in payload
        assert "regions" in payload
        assert "captures" in payload
        assert len(payload["regions"]) >= 1
        assert len(payload["captures"]) >= 1
        assert output_dir.exists()
        assert (output_dir / "manifest.json").exists()

    def test_research_dry_run_writes_no_images(self, runner: CliRunner, tmp_path: Path):
        video_path = _copy_video(tmp_path)
        output_dir = tmp_path / "research_pkg_dry"

        result = runner.invoke(
            main,
            [
                "research",
                str(video_path),
                "--transcript", str(TRANSCRIPT_FIXTURE),
                "--query", "reporter",
                "--output", str(output_dir),
                "--dry-run",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["dry_run"] is True
        assert len(payload["regions"]) >= 1
        for region in payload["regions"]:
            assert "expected_candidate_count" in region
        assert not output_dir.exists()


class TestFrameCommand:
    def test_frame_single_timestamp_json(self, runner: CliRunner, tmp_path: Path):
        video_path = _copy_video(tmp_path)

        result = runner.invoke(main, ["frame", str(video_path), "--timestamp", "0.5", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["timestamp_seconds"] == pytest.approx(0.5)
        image_path = Path(payload["image_path"])
        assert image_path.exists()
        assert image_path.stat().st_size > 0


class TestScenesCommand:
    def test_scenes_json_list(self, runner: CliRunner, tmp_path: Path):
        video_path = _copy_video(tmp_path)

        result = runner.invoke(main, ["scenes", str(video_path), "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) >= 1
        for item in payload:
            assert "timestamp_seconds" in item
            assert "score" in item


class TestTranscriptCommands:
    def test_transcript_search_json(self, runner: CliRunner):
        result = runner.invoke(
            main, ["transcript", "search", str(TRANSCRIPT_FIXTURE), "greenscreen", "--json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) >= 1
        assert "greenscreen" in payload[0]["text"].lower()

    def test_transcript_context_json(self, runner: CliRunner):
        result = runner.invoke(
            main, ["transcript", "context", str(TRANSCRIPT_FIXTURE), "1.0", "--seconds", "2.0", "--json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert len(payload) >= 1


def test_ss11_integration_evidence_exists():
    evidence_path = Path(__file__).parent / "ss11-integration-evidence.md"
    assert evidence_path.exists()
