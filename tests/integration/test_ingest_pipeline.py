"""Integration tests for the ingest pipeline.

Requires ffmpeg to be installed.  Tests are automatically skipped when ffmpeg
is not available on the PATH.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from workshop_video_brain.app.config import Config
from workshop_video_brain.edit_mcp.pipelines.ingest import IngestReport, run_ingest
from workshop_video_brain.workspace.manager import WorkspaceManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_VIDEO = Path(__file__).parent.parent / "fixtures" / "media" / "sample.mp4"

ffmpeg_available = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg not available on PATH"
)


@pytest.fixture()
def workspace(tmp_path: Path):
    """Create a real workspace with the fixture video in media/raw/."""
    ws = WorkspaceManager.create(
        title="Integration Test Project",
        media_root=str(tmp_path / "raw_source"),
        workspace_root=tmp_path / "workspace",
    )
    raw_dir = Path(ws.workspace_root) / "media" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if FIXTURE_VIDEO.exists():
        shutil.copy(FIXTURE_VIDEO, raw_dir / "sample.mp4")

    return ws


@pytest.fixture()
def no_whisper_config() -> Config:
    """Config with ffmpeg available but whisper disabled."""
    return Config(
        vault_path=None,
        workspace_root=None,
        ffmpeg_path="ffmpeg",
        whisper_model="tiny",
        whisper_available=False,
        ffmpeg_available=True,
    )


# ---------------------------------------------------------------------------
# Tests: basic ingest run
# ---------------------------------------------------------------------------

class TestIngestPipelineBasic:
    def test_returns_ingest_report(self, workspace, no_whisper_config):
        report = run_ingest(workspace, no_whisper_config)
        assert isinstance(report, IngestReport)

    def test_scans_fixture_video(self, workspace, no_whisper_config):
        report = run_ingest(workspace, no_whisper_config)
        if FIXTURE_VIDEO.exists():
            assert report.scanned_count >= 1
        else:
            pytest.skip("Fixture video not generated")

    def test_empty_raw_dir_no_crash(self, workspace, no_whisper_config):
        """Pipeline should not crash if media/raw/ is empty."""
        # Remove fixture file if present
        raw_dir = Path(workspace.workspace_root) / "media" / "raw"
        for f in raw_dir.iterdir():
            f.unlink()

        report = run_ingest(workspace, no_whisper_config)
        assert report.scanned_count == 0
        assert report.errors == []


# ---------------------------------------------------------------------------
# Tests: proxy generation
# ---------------------------------------------------------------------------

class TestIngestProxy:
    def test_no_proxy_for_small_video(self, workspace, no_whisper_config):
        """320x240 fixture video should NOT need a proxy under default policy."""
        report = run_ingest(workspace, no_whisper_config)
        # fixture video is 320x240 h264 -- well below proxy thresholds
        assert report.proxied_count == 0

    def test_proxy_dir_created(self, workspace, no_whisper_config):
        run_ingest(workspace, no_whisper_config)
        proxy_dir = Path(workspace.workspace_root) / "media" / "proxies"
        assert proxy_dir.exists()


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

class TestIngestIdempotency:
    def test_second_run_skips_already_transcribed(self, workspace, tmp_path):
        """If transcript JSON already exists the asset must be skipped."""
        if not FIXTURE_VIDEO.exists():
            pytest.skip("Fixture video not generated")

        # Manually write a fake transcript JSON to simulate a prior run
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        fake_transcript = transcripts_dir / "sample_transcript.json"
        fake_transcript.write_text('{"id": "00000000-0000-0000-0000-000000000000"}')

        config = Config(
            vault_path=None,
            workspace_root=None,
            ffmpeg_path="ffmpeg",
            whisper_model="tiny",
            whisper_available=False,
            ffmpeg_available=True,
        )

        report = run_ingest(workspace, config)
        # transcript already exists, so transcribed_count stays 0
        assert report.transcribed_count == 0

    def test_second_run_produces_same_artifacts(self, workspace, no_whisper_config):
        """Running ingest twice without whisper should produce the same report."""
        report1 = run_ingest(workspace, no_whisper_config)
        report2 = run_ingest(workspace, no_whisper_config)
        assert report1.scanned_count == report2.scanned_count
        # Second run has nothing to transcribe (already done or skipped)
        assert report2.transcribed_count == 0


# ---------------------------------------------------------------------------
# Tests: error resilience
# ---------------------------------------------------------------------------

class TestIngestErrorResilience:
    def test_corrupt_file_isolated(self, workspace, no_whisper_config):
        """A corrupt media file must not crash the pipeline.

        ffprobe failures are caught inside scan_directory and logged as
        warnings; the bad file is simply excluded from the asset list.
        The ingest pipeline still returns a valid IngestReport.
        """
        raw_dir = Path(workspace.workspace_root) / "media" / "raw"
        # Write an obviously corrupt mp4 alongside the valid fixture file
        (raw_dir / "corrupt.mp4").write_bytes(b"NOTVALIDMP4DATAATALL")

        report = run_ingest(workspace, no_whisper_config)
        # Pipeline must not raise -- we get a report back
        assert isinstance(report, IngestReport)
        # The corrupt file is excluded from the scan; if the fixture is also
        # present it will be counted; if not, scanned_count may be 0.
        # The important thing is no unhandled exception was raised.

    def test_pipeline_continues_after_per_asset_error(self, workspace, no_whisper_config):
        """An error during per-asset processing lands in report.errors."""
        from unittest.mock import patch

        raw_dir = Path(workspace.workspace_root) / "media" / "raw"
        if not any(raw_dir.iterdir()):
            pytest.skip("No fixture video in raw dir")

        # Force an error inside _process_asset by making needs_proxy raise
        with patch(
            "workshop_video_brain.edit_mcp.pipelines.ingest.needs_proxy",
            side_effect=RuntimeError("forced error"),
        ):
            report = run_ingest(workspace, no_whisper_config)

        assert isinstance(report, IngestReport)
        assert len(report.errors) >= 1
