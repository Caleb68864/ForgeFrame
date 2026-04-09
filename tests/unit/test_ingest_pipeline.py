"""Tests for the ingest pipeline (PL-01)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.app.config import Config
from workshop_video_brain.core.models import (
    MediaAsset,
    ProxyStatus,
    TranscriptStatus,
    Workspace,
)
from workshop_video_brain.core.models.project import VideoProject
from workshop_video_brain.edit_mcp.pipelines.ingest import (
    IngestReport,
    _transcript_json_path,
    run_ingest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_workspace(tmp_path: Path) -> Workspace:
    return Workspace(
        workspace_root=str(tmp_path),
        media_root=str(tmp_path / "media"),
        project=VideoProject(title="Test Project"),
    )


def make_config(ffmpeg_available: bool = True, whisper_available: bool = True) -> Config:
    return Config(
        vault_path=None,
        workspace_root=None,
        ffmpeg_path="ffmpeg",
        whisper_model="small",
        whisper_available=whisper_available,
        ffmpeg_available=ffmpeg_available,
    )


def make_asset(tmp_path: Path, name: str = "clip.mp4") -> MediaAsset:
    return MediaAsset(path=str(tmp_path / "media" / "raw" / name))


INGEST_MOD = "workshop_video_brain.edit_mcp.pipelines.ingest"


# ---------------------------------------------------------------------------
# TestIngestReport
# ---------------------------------------------------------------------------


class TestIngestReport:
    def test_default_field_values(self):
        r = IngestReport()
        assert r.scanned_count == 0
        assert r.proxied_count == 0
        assert r.transcribed_count == 0
        assert r.silence_detected_count == 0
        assert r.errors == []

    def test_errors_field_is_independent_list(self):
        r1 = IngestReport()
        r2 = IngestReport()
        r1.errors.append("oops")
        assert r2.errors == []


# ---------------------------------------------------------------------------
# TestRunIngestEmptyWorkspace
# ---------------------------------------------------------------------------


class TestRunIngestEmptyWorkspace:
    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_returns_report_with_zero_counts_when_no_assets(
        self, mock_scan, mock_wm, tmp_path
    ):
        mock_scan.return_value = []
        report = run_ingest(make_workspace(tmp_path), make_config())
        assert report.scanned_count == 0
        assert report.proxied_count == 0
        assert report.transcribed_count == 0
        assert report.silence_detected_count == 0
        assert report.errors == []


# ---------------------------------------------------------------------------
# TestRunIngestHappyPath
# ---------------------------------------------------------------------------


def _setup_happy_path_mocks(mock_scan, mock_needs_proxy, mock_proxy_path_for,
                             mock_generate_proxy, mock_whisper, mock_detect_silence,
                             tmp_path: Path, name: str = "clip.mp4"):
    asset = make_asset(tmp_path, name)
    mock_scan.return_value = [asset]
    mock_needs_proxy.return_value = True

    fake_proxy = MagicMock()
    fake_proxy.exists.return_value = False
    mock_proxy_path_for.return_value = fake_proxy
    mock_generate_proxy.return_value = Path(str(tmp_path / "proxies" / "clip_proxy.mp4"))

    mock_transcript = MagicMock()
    mock_transcript.raw_text = "hello world"
    mock_whisper.is_available.return_value = True
    mock_whisper.extract_audio.return_value = None
    mock_whisper.transcribe.return_value = mock_transcript
    mock_whisper.transcript_to_json.return_value = '{"segments": []}'
    mock_whisper.transcript_to_srt.return_value = ""

    mock_detect_silence.return_value = [(2.5, 5.0)]
    return asset


class TestRunIngestHappyPath:
    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.generate_proxy")
    @patch(f"{INGEST_MOD}.proxy_path_for")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_single_asset_fully_processed(
        self, mock_scan, mock_needs_proxy, mock_proxy_path_for,
        mock_generate_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        _setup_happy_path_mocks(mock_scan, mock_needs_proxy, mock_proxy_path_for,
                                mock_generate_proxy, mock_whisper, mock_detect_silence,
                                tmp_path)
        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.scanned_count == 1
        assert report.proxied_count == 1
        assert report.transcribed_count == 1
        assert report.silence_detected_count == 1
        assert report.errors == []

        transcripts_dir = tmp_path / "transcripts"
        assert any(transcripts_dir.glob("*_transcript.json"))
        markers_dir = tmp_path / "markers"
        assert any(markers_dir.glob("*_silence.json"))

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.generate_proxy")
    @patch(f"{INGEST_MOD}.proxy_path_for")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_idempotency_skips_asset_when_transcript_exists(
        self, mock_scan, mock_needs_proxy, mock_proxy_path_for,
        mock_generate_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        asset = make_asset(tmp_path)
        mock_scan.return_value = [asset]
        mock_needs_proxy.return_value = True
        fake_proxy = MagicMock()
        fake_proxy.exists.return_value = False
        mock_proxy_path_for.return_value = fake_proxy
        mock_whisper.is_available.return_value = True

        # Pre-create the transcript JSON
        transcripts_dir = tmp_path / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        json_path = _transcript_json_path(transcripts_dir, asset)
        json_path.write_text("{}", encoding="utf-8")

        report = run_ingest(make_workspace(tmp_path), make_config())

        mock_whisper.transcribe.assert_not_called()
        assert report.transcribed_count == 0

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.generate_proxy")
    @patch(f"{INGEST_MOD}.proxy_path_for")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_multiple_assets_all_processed(
        self, mock_scan, mock_needs_proxy, mock_proxy_path_for,
        mock_generate_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        asset1 = make_asset(tmp_path, "clip1.mp4")
        asset2 = make_asset(tmp_path, "clip2.mp4")
        mock_scan.return_value = [asset1, asset2]
        mock_needs_proxy.return_value = True

        fake_proxy = MagicMock()
        fake_proxy.exists.return_value = False
        mock_proxy_path_for.return_value = fake_proxy
        mock_generate_proxy.return_value = Path(str(tmp_path / "proxy.mp4"))

        mock_transcript = MagicMock()
        mock_transcript.raw_text = "text"
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.return_value = mock_transcript
        mock_whisper.transcript_to_json.return_value = '{"segments": []}'
        mock_whisper.transcript_to_srt.return_value = ""
        mock_detect_silence.return_value = []

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.scanned_count == 2
        assert report.transcribed_count == 2


# ---------------------------------------------------------------------------
# TestRunIngestPartialFailures
# ---------------------------------------------------------------------------


class TestRunIngestPartialFailures:
    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.generate_proxy")
    @patch(f"{INGEST_MOD}.proxy_path_for")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_proxy_failure_does_not_stop_transcription(
        self, mock_scan, mock_needs_proxy, mock_proxy_path_for,
        mock_generate_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        asset = make_asset(tmp_path)
        mock_scan.return_value = [asset]
        mock_needs_proxy.return_value = True

        fake_proxy = MagicMock()
        fake_proxy.exists.return_value = False
        mock_proxy_path_for.return_value = fake_proxy
        mock_generate_proxy.side_effect = RuntimeError("proxy failed")

        mock_transcript = MagicMock()
        mock_transcript.raw_text = "text"
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.return_value = mock_transcript
        mock_whisper.transcript_to_json.return_value = '{"segments": []}'
        mock_whisper.transcript_to_srt.return_value = ""
        mock_detect_silence.return_value = []

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.proxied_count == 0
        assert report.transcribed_count == 1
        assert asset.proxy_status == ProxyStatus.failed.value

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_whisper_unavailable_skips_transcription(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]
        mock_needs_proxy.return_value = False
        mock_whisper.is_available.return_value = False

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.transcribed_count == 0
        assert report.errors == []

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.generate_proxy")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_ffmpeg_unavailable_skips_proxy_and_transcription(
        self, mock_scan, mock_needs_proxy, mock_generate_proxy, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]

        with patch(f"{INGEST_MOD}.whisper_engine") as mock_whisper:
            report = run_ingest(make_workspace(tmp_path), make_config(ffmpeg_available=False))

        mock_generate_proxy.assert_not_called()
        mock_whisper.transcribe.assert_not_called()

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_audio_extraction_failure_skips_asset(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]
        mock_needs_proxy.return_value = False
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.side_effect = RuntimeError("audio fail")

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.transcribed_count == 0
        mock_detect_silence.assert_not_called()

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_transcription_failure_sets_failed_status(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        asset = make_asset(tmp_path)
        mock_scan.return_value = [asset]
        mock_needs_proxy.return_value = False
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.side_effect = RuntimeError("transcribe fail")

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert asset.transcript_status == TranscriptStatus.failed.value
        assert report.transcribed_count == 0

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_silence_detection_failure_does_not_propagate(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]
        mock_needs_proxy.return_value = False
        mock_transcript = MagicMock()
        mock_transcript.raw_text = "text"
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.return_value = mock_transcript
        mock_whisper.transcript_to_json.return_value = '{"segments": []}'
        mock_whisper.transcript_to_srt.return_value = ""
        mock_detect_silence.side_effect = RuntimeError("silence fail")

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.transcribed_count == 1
        assert report.silence_detected_count == 0

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_asset_level_exception_recorded_in_errors(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        asset1 = make_asset(tmp_path, "clip1.mp4")
        asset2 = make_asset(tmp_path, "clip2.mp4")
        mock_scan.return_value = [asset1, asset2]

        with patch(f"{INGEST_MOD}._process_asset") as mock_process:
            call_count = [0]

            def side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("asset 1 exploded")

            mock_process.side_effect = side_effect
            report = run_ingest(make_workspace(tmp_path), make_config())

        assert len(report.errors) == 1
        assert report.scanned_count == 2


# ---------------------------------------------------------------------------
# TestRunIngestSilenceDetection
# ---------------------------------------------------------------------------


class TestRunIngestSilenceDetection:
    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_silence_json_written_with_correct_structure(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]
        mock_needs_proxy.return_value = False
        mock_transcript = MagicMock()
        mock_transcript.raw_text = "text"
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.return_value = mock_transcript
        mock_whisper.transcript_to_json.return_value = '{"segments": []}'
        mock_whisper.transcript_to_srt.return_value = ""
        mock_detect_silence.return_value = [(1.0, 3.5), (10.0, 12.0)]

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.silence_detected_count == 1
        silence_files = list((tmp_path / "markers").glob("*_silence.json"))
        assert len(silence_files) == 1
        data = json.loads(silence_files[0].read_text())
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"start": 1.0, "end": 3.5}
        assert data[1] == {"start": 10.0, "end": 12.0}

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.detect_silence")
    @patch(f"{INGEST_MOD}.whisper_engine")
    @patch(f"{INGEST_MOD}.needs_proxy")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_no_silence_does_not_increment_count(
        self, mock_scan, mock_needs_proxy, mock_whisper, mock_detect_silence, mock_wm, tmp_path
    ):
        mock_scan.return_value = [make_asset(tmp_path)]
        mock_needs_proxy.return_value = False
        mock_transcript = MagicMock()
        mock_transcript.raw_text = "text"
        mock_whisper.is_available.return_value = True
        mock_whisper.extract_audio.return_value = None
        mock_whisper.transcribe.return_value = mock_transcript
        mock_whisper.transcript_to_json.return_value = '{"segments": []}'
        mock_whisper.transcript_to_srt.return_value = ""
        mock_detect_silence.return_value = []

        report = run_ingest(make_workspace(tmp_path), make_config())

        assert report.silence_detected_count == 0


# ---------------------------------------------------------------------------
# TestRunIngestManifestSave
# ---------------------------------------------------------------------------


class TestRunIngestManifestSave:
    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_manifest_saved_after_all_assets(self, mock_scan, mock_wm, tmp_path):
        mock_scan.return_value = []
        run_ingest(make_workspace(tmp_path), make_config())
        mock_wm.save_manifest.assert_called_once()

    @patch(f"{INGEST_MOD}.WorkspaceManager")
    @patch(f"{INGEST_MOD}.scan_directory")
    def test_manifest_save_failure_does_not_raise(self, mock_scan, mock_wm, tmp_path):
        mock_scan.return_value = []
        mock_wm.save_manifest.side_effect = IOError("disk full")
        # Should not raise
        report = run_ingest(make_workspace(tmp_path), make_config())
        assert report.scanned_count == 0
