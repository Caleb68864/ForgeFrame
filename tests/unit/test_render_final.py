"""Tests for the full render pipeline."""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from workshop_video_brain.edit_mcp.pipelines.render_final import (
    RenderResult,
    render_final,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace_with_project(tmp_path: Path) -> Path:
    """Create a workspace with a .kdenlive project file."""
    # Workspace structure
    (tmp_path / "workspace.yaml").write_text("title: Test Project\n")
    (tmp_path / "renders").mkdir()

    # Create a minimal .kdenlive file
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    kdenlive = project_dir / "test_project.kdenlive"
    kdenlive.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<mlt><playlist id="main_bin"/></mlt>'
    )

    return tmp_path


@pytest.fixture
def workspace_no_project(tmp_path: Path) -> Path:
    """Workspace without any .kdenlive file."""
    (tmp_path / "workspace.yaml").write_text("title: Empty\n")
    (tmp_path / "renders").mkdir()
    return tmp_path


@pytest.fixture
def mock_profile():
    """A mock RenderProfile."""
    profile = MagicMock()
    profile.name = "youtube-1080p"
    profile.video_codec = "libx264"
    profile.audio_codec = "aac"
    profile.width = 1920
    profile.height = 1080
    profile.fps = 30.0
    profile.video_bitrate = "8M"
    profile.audio_bitrate = "192k"
    profile.extra_args = []
    profile.fast_start = True
    profile.movflags = "+faststart"
    return profile


# ---------------------------------------------------------------------------
# RenderResult dataclass
# ---------------------------------------------------------------------------

class TestRenderResult:
    def test_fields(self):
        r = RenderResult(
            output_path="/tmp/out.mp4",
            profile_used="youtube-1080p",
            duration_seconds=120.5,
            file_size_bytes=15_000_000,
            codec_info="libx264 / aac",
        )
        assert r.profile_used == "youtube-1080p"
        assert r.duration_seconds == pytest.approx(120.5)
        d = asdict(r)
        assert "codec_info" in d

    def test_serializable(self):
        r = RenderResult(
            output_path="/tmp/out.mp4",
            profile_used="test",
            duration_seconds=0.0,
            file_size_bytes=0,
            codec_info="",
        )
        d = asdict(r)
        assert isinstance(d["output_path"], str)


# ---------------------------------------------------------------------------
# render_final pipeline
# ---------------------------------------------------------------------------

class TestRenderFinal:
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_successful_render(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Successful render returns RenderResult with output path."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")

        assert isinstance(result, RenderResult)
        assert result.profile_used == "youtube-1080p"
        assert "renders" in str(result.output_path)
        assert result.output_path.suffix == ".mp4"

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_missing_codec_raises(
        self, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Missing codec should raise RuntimeError with actionable message."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = False

        with pytest.raises(RuntimeError, match="not found"):
            render_final(workspace_with_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_no_project_file_raises(
        self, mock_load_profile, mock_codec_check,
        workspace_no_project: Path, mock_profile,
    ):
        """No .kdenlive project should raise FileNotFoundError."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True

        with pytest.raises(FileNotFoundError, match="No .kdenlive project"):
            render_final(workspace_no_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_invalid_profile_propagates(
        self, mock_load_profile, mock_codec_check,
        workspace_with_project: Path,
    ):
        """Invalid profile name should propagate FileNotFoundError from load_profile."""
        mock_load_profile.side_effect = FileNotFoundError("Profile 'bogus' not found")

        with pytest.raises(FileNotFoundError, match="bogus"):
            render_final(workspace_with_project, "bogus")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_custom_output_name(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Custom output_name should appear in the output filename."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(
            workspace_with_project, "youtube-1080p", output_name="final_cut",
        )

        assert "final_cut" in result.output_path.name

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_ffmpeg_failure_raises(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Non-zero FFmpeg exit should raise RuntimeError."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="Encoding error",
        )

        with pytest.raises(RuntimeError, match="Render failed"):
            render_final(workspace_with_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_output_in_renders_dir(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Output path should be inside workspace/renders/."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")

        assert result.output_path.parent == workspace_with_project / "renders"

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_renders_dir_created_if_missing(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """renders/ dir should be created if it does not exist."""
        import shutil
        renders_dir = workspace_with_project / "renders"
        if renders_dir.exists():
            shutil.rmtree(renders_dir)

        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")
        assert result.output_path.parent.exists()


# ---------------------------------------------------------------------------
# FFmpeg command construction
# ---------------------------------------------------------------------------

class TestFFmpegCommand:
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_command_includes_profile_settings(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """FFmpeg command should include codec, bitrate, resolution from profile."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        render_final(workspace_with_project, "youtube-1080p")

        call_args = mock_subprocess.run.call_args[0][0]
        cmd_str = " ".join(str(a) for a in call_args)
        assert "libx264" in cmd_str
        assert "8M" in cmd_str

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_fast_start_flag(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """fast_start=True should add -movflags +faststart to the command."""
        mock_profile.fast_start = True
        mock_profile.movflags = "+faststart"
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        render_final(workspace_with_project, "youtube-1080p")

        call_args = mock_subprocess.run.call_args[0][0]
        cmd_str = " ".join(str(a) for a in call_args)
        assert "faststart" in cmd_str
