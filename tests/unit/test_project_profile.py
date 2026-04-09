"""Tests for project profile setup pipeline."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from workshop_video_brain.edit_mcp.pipelines.project_profile import (
    set_project_profile,
    match_profile_to_source,
)


def _make_project(width=1920, height=1080, fps=30.0, colorspace="709"):
    """Create a minimal KdenliveProject with profile attrs."""
    from workshop_video_brain.core.models.kdenlive import KdenliveProject, ProjectProfile
    profile = ProjectProfile(width=width, height=height, fps=fps, colorspace=colorspace)
    return KdenliveProject(profile=profile)


class TestSetProjectProfile:
    def test_sets_resolution(self):
        project = _make_project()
        result = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1)
        assert result.profile.width == 3840
        assert result.profile.height == 2160

    def test_sets_fps(self):
        project = _make_project()
        result = set_project_profile(project, width=1920, height=1080, fps_num=60, fps_den=1)
        assert result.profile.fps == 60.0

    def test_sets_colorspace(self):
        project = _make_project()
        result = set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1, colorspace=601)
        assert result.profile.colorspace == "601"

    def test_default_colorspace_709(self):
        project = _make_project(colorspace="601")
        result = set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1)
        assert result.profile.colorspace == "709"

    def test_deep_copies_project(self):
        project = _make_project()
        result = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1)
        assert result is not project
        assert project.profile.width == 1920  # original unchanged

    def test_invalid_colorspace_raises(self):
        project = _make_project()
        with pytest.raises(ValueError, match="colorspace"):
            set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1, colorspace=999)

    def test_fractional_fps_stored(self):
        """29.97 fps (30000/1001) should store correctly as float."""
        project = _make_project()
        result = set_project_profile(project, width=1920, height=1080, fps_num=30000, fps_den=1001)
        assert abs(result.profile.fps - 29.97) < 0.01


class TestMatchProfileToSource:
    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_1080p30(self, mock_probe):
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 30.0
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result == {"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "colorspace": 709}

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_4k24(self, mock_probe):
        asset = MagicMock()
        asset.width = 3840
        asset.height = 2160
        asset.fps = 24.0
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result == {"width": 3840, "height": 2160, "fps_num": 24, "fps_den": 1, "colorspace": 709}

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_fractional_fps(self, mock_probe):
        """29.97 fps should produce 30000/1001."""
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 29.97
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result["fps_num"] == 30000
        assert result["fps_den"] == 1001

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_23976(self, mock_probe):
        """23.976 fps should produce 24000/1001."""
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 23.976
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result["fps_num"] == 24000
        assert result["fps_den"] == 1001


class TestRoundTrip:
    """Set profile -> serialize -> parse -> verify attributes."""

    def test_set_serialize_parse_roundtrip(self):
        """Integration-style: set profile, serialize to XML, parse back, verify."""
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        import tempfile

        project = _make_project()
        updated = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1, colorspace=709)

        with tempfile.NamedTemporaryFile(suffix=".kdenlive", delete=False) as f:
            tmp_path = Path(f.name)

        serialize_project(updated, tmp_path)
        parsed = parse_project(tmp_path)

        assert parsed.profile.width == 3840
        assert parsed.profile.height == 2160
        assert parsed.profile.fps == 24.0
        assert parsed.profile.colorspace == "709"
