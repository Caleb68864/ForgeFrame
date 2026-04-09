"""Tests for VFR detection and CFR transcode pipeline."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.edit_mcp.pipelines.vfr_check import (
    VFRFile,
    VFRReport,
    check_vfr,
    transcode_to_cfr,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_media_asset(path: str, is_vfr: bool, fps: float = 30.0):
    """Create a mock MediaAsset with the fields we need."""
    asset = MagicMock()
    asset.path = path
    asset.is_vfr = is_vfr
    asset.fps = fps
    # Simulate r_frame_rate and avg_frame_rate strings
    if is_vfr:
        asset.r_frame_rate = "30000/1001"
        asset.avg_frame_rate = "25/1"
    else:
        asset.r_frame_rate = "30/1"
        asset.avg_frame_rate = "30/1"
    return asset


@pytest.fixture
def workspace_with_vfr(tmp_path: Path) -> Path:
    """Create a workspace with mixed VFR/CFR files."""
    media = tmp_path / "media" / "raw"
    media.mkdir(parents=True)
    (media / "clip_vfr.mp4").write_text("fake")
    (media / "clip_cfr.mp4").write_text("fake")
    (media / "notes.txt").write_text("not a video")
    return tmp_path


@pytest.fixture
def workspace_all_cfr(tmp_path: Path) -> Path:
    """Create a workspace with only CFR files."""
    media = tmp_path / "media" / "raw"
    media.mkdir(parents=True)
    (media / "a.mp4").write_text("fake")
    (media / "b.mov").write_text("fake")
    return tmp_path


@pytest.fixture
def workspace_empty(tmp_path: Path) -> Path:
    """Workspace with no video files."""
    (tmp_path / "media" / "raw").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# VFRReport / VFRFile dataclass tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_vfr_file_fields(self):
        vf = VFRFile(
            path="/tmp/clip.mp4",
            r_frame_rate="30000/1001",
            avg_frame_rate="25/1",
            divergence_pct=16.7,
        )
        assert vf.divergence_pct == pytest.approx(16.7)
        d = asdict(vf)
        assert "r_frame_rate" in d

    def test_vfr_report_all_cfr(self):
        report = VFRReport(files_checked=3, vfr_files=[], all_cfr=True)
        assert report.all_cfr is True
        assert report.files_checked == 3

    def test_vfr_report_has_vfr(self):
        vf = VFRFile("/x.mp4", "30000/1001", "25/1", 16.7)
        report = VFRReport(files_checked=2, vfr_files=[vf], all_cfr=False)
        assert report.all_cfr is False
        assert len(report.vfr_files) == 1


# ---------------------------------------------------------------------------
# check_vfr pipeline tests
# ---------------------------------------------------------------------------

class TestCheckVFR:
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_detects_vfr_files(self, mock_probe, workspace_with_vfr: Path):
        """VFR files should appear in the report."""
        def side_effect(path):
            if "vfr" in path.name:
                return _make_media_asset(str(path), is_vfr=True)
            return _make_media_asset(str(path), is_vfr=False)

        mock_probe.side_effect = side_effect

        report = check_vfr(workspace_with_vfr)
        assert report.files_checked == 2  # 2 video files, not txt
        assert report.all_cfr is False
        assert len(report.vfr_files) == 1
        assert "vfr" in str(report.vfr_files[0].path)

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_all_cfr_workspace(self, mock_probe, workspace_all_cfr: Path):
        """All-CFR workspace should report all_cfr=True."""
        mock_probe.return_value = _make_media_asset("/x.mp4", is_vfr=False)

        report = check_vfr(workspace_all_cfr)
        assert report.all_cfr is True
        assert len(report.vfr_files) == 0

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_empty_workspace(self, mock_probe, workspace_empty: Path):
        """Empty workspace should return zero files checked."""
        report = check_vfr(workspace_empty)
        assert report.files_checked == 0
        assert report.all_cfr is True
        mock_probe.assert_not_called()

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_probe_error_skips_file(self, mock_probe, workspace_all_cfr: Path):
        """If probe_media raises, skip that file and continue."""
        mock_probe.side_effect = Exception("ffprobe failed")
        report = check_vfr(workspace_all_cfr)
        # Should not raise; files checked may be 0 due to errors
        assert report.all_cfr is True


# ---------------------------------------------------------------------------
# transcode_to_cfr tests
# ---------------------------------------------------------------------------

class TestTranscodeToCFR:
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_output_path_has_cfr_suffix(self, mock_subprocess, tmp_path: Path):
        """Output should be alongside source with _cfr suffix."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        result = transcode_to_cfr(source, target_fps=30)

        assert result.name == "clip_cfr.mp4"
        assert result.parent == source.parent

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_ffmpeg_command_includes_vsync_cfr(self, mock_subprocess, tmp_path: Path):
        """FFmpeg command should include -vsync cfr -r {fps}."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        transcode_to_cfr(source, target_fps=30)

        call_args = mock_subprocess.run.call_args[0][0]
        assert "cfr" in call_args
        assert "-r" in call_args
        assert "30" in call_args

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_auto_detect_fps_when_none(self, mock_probe, mock_subprocess, tmp_path: Path):
        """When target_fps is None, use avg_frame_rate from probe."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_probe.return_value = _make_media_asset(str(source), is_vfr=True, fps=24.0)
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        transcode_to_cfr(source, target_fps=None)

        call_args = mock_subprocess.run.call_args[0][0]
        assert "24" in call_args

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_ffmpeg_failure_raises(self, mock_subprocess, tmp_path: Path):
        """Non-zero FFmpeg exit should raise RuntimeError."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="Error encoding",
        )

        with pytest.raises(RuntimeError, match="FFmpeg transcode failed"):
            transcode_to_cfr(source, target_fps=30)
