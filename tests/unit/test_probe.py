"""Unit tests for the ffprobe adapter."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    DEFAULT_EXTENSIONS,
    probe_media,
    scan_directory,
)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

FFPROBE_VIDEO_OUTPUT = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "25/1",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "sample_rate": "48000",
        },
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "120.5",
        "size": "1048576",
        "bit_rate": "5000000",
    },
}

FFPROBE_AUDIO_ONLY_OUTPUT = {
    "streams": [
        {
            "codec_type": "audio",
            "codec_name": "flac",
            "channels": 1,
            "sample_rate": "44100",
        },
    ],
    "format": {
        "format_name": "flac",
        "duration": "60.0",
        "size": "512000",
        "bit_rate": "1000000",
    },
}

FFPROBE_HEVC_OUTPUT = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "hevc",
            "width": 3840,
            "height": 2160,
            "r_frame_rate": "60/1",
        },
    ],
    "format": {
        "format_name": "matroska,webm",
        "duration": "30.0",
        "size": "500000000",
        "bit_rate": "80000000",
    },
}


def _make_subprocess_result(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.stdout = json.dumps(data)
    return mock


# ---------------------------------------------------------------------------
# Tests: probe_media
# ---------------------------------------------------------------------------

class TestProbeMedia:
    def _patch_run(self, data: dict, tmp_path: Path):
        """Create a fake file and patch subprocess.run to return *data*."""
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00" * 65536)  # 64 KB of zeros for hash

        mock_result = _make_subprocess_result(data)

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            return probe_media(fake_file)

    def test_video_codec_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.video_codec == "h264"

    def test_audio_codec_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.audio_codec == "aac"

    def test_resolution_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.width == 1920
        assert asset.height == 1080

    def test_duration_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.duration == pytest.approx(120.5)

    def test_fps_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.fps == pytest.approx(25.0)

    def test_fps_60(self, tmp_path):
        asset = self._patch_run(FFPROBE_HEVC_OUTPUT, tmp_path)
        assert asset.fps == pytest.approx(60.0)

    def test_bitrate_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.bitrate == 5_000_000

    def test_file_size_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.file_size == 1_048_576

    def test_channels_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.channels == 2

    def test_sample_rate_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.sample_rate == 48000

    def test_hash_is_md5_hex(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert len(asset.hash) == 32
        assert all(c in "0123456789abcdef" for c in asset.hash)

    def test_container_extracted(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        # container is first token of format_name
        assert asset.container == "mov"

    def test_media_type_video(self, tmp_path):
        asset = self._patch_run(FFPROBE_VIDEO_OUTPUT, tmp_path)
        assert asset.media_type == "video"

    def test_media_type_audio(self, tmp_path):
        asset = self._patch_run(FFPROBE_AUDIO_ONLY_OUTPUT, tmp_path)
        assert asset.media_type == "audio"

    def test_path_stored(self, tmp_path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00" * 65536)
        mock_result = _make_subprocess_result(FFPROBE_VIDEO_OUTPUT)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            asset = probe_media(fake_file)
        assert asset.path == str(fake_file)

    def test_hevc_asset_fields(self, tmp_path):
        asset = self._patch_run(FFPROBE_HEVC_OUTPUT, tmp_path)
        assert asset.video_codec == "hevc"
        assert asset.width == 3840
        assert asset.height == 2160
        assert asset.bitrate == 80_000_000


# ---------------------------------------------------------------------------
# Tests: scan_directory
# ---------------------------------------------------------------------------

class TestScanDirectory:
    def test_finds_video_files(self, tmp_path):
        (tmp_path / "clip.mp4").write_bytes(b"\x00" * 65536)

        mock_result = _make_subprocess_result(FFPROBE_VIDEO_OUTPUT)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            assets = scan_directory(tmp_path)

        assert len(assets) == 1
        assert "clip.mp4" in assets[0].path

    def test_ignores_non_media_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "clip.mp4").write_bytes(b"\x00" * 65536)

        mock_result = _make_subprocess_result(FFPROBE_VIDEO_OUTPUT)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            assets = scan_directory(tmp_path)

        assert len(assets) == 1

    def test_scans_recursively(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.mkv").write_bytes(b"\x00" * 65536)

        mock_result = _make_subprocess_result(FFPROBE_VIDEO_OUTPUT)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            assets = scan_directory(tmp_path)

        assert len(assets) == 1
        assert "nested.mkv" in assets[0].path

    def test_bad_file_does_not_crash(self, tmp_path):
        (tmp_path / "good.mp4").write_bytes(b"\x00" * 65536)
        (tmp_path / "bad.mp4").write_bytes(b"\x00" * 65536)

        good_result = _make_subprocess_result(FFPROBE_VIDEO_OUTPUT)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "bad.mp4" in " ".join(str(c) for c in cmd):
                raise subprocess.CalledProcessError(1, cmd)
            return good_result

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            side_effect=fake_run,
        ):
            assets = scan_directory(tmp_path)

        # Only the good file returned; no exception raised
        assert len(assets) == 1

    def test_custom_extensions(self, tmp_path):
        (tmp_path / "video.mp4").write_bytes(b"\x00" * 65536)
        (tmp_path / "audio.mp3").write_bytes(b"\x00" * 65536)

        mock_result = _make_subprocess_result(FFPROBE_AUDIO_ONLY_OUTPUT)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            return_value=mock_result,
        ):
            assets = scan_directory(tmp_path, extensions={".mp3"})

        assert len(assets) == 1
        assert "audio.mp3" in assets[0].path

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assets = scan_directory(tmp_path)
        assert assets == []

    def test_default_extensions_coverage(self):
        expected = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mts", ".m2ts", ".mp3", ".wav", ".flac"}
        assert expected == DEFAULT_EXTENSIONS
