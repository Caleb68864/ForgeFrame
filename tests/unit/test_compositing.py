"""Tests for compositing pipeline -- PiP and wipe tools."""
from copy import deepcopy
from unittest.mock import patch
import pytest

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.edit_mcp.pipelines.compositing import (
    get_pip_layout,
    apply_pip,
    apply_wipe,
)

FRAME_W = 1920
FRAME_H = 1080
MARGIN = 20


class TestGetPipLayout:
    def test_bottom_right(self):
        layout = get_pip_layout(PipPreset.bottom_right, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.width == 480
        assert layout.height == 270
        assert layout.x == FRAME_W - 480 - MARGIN  # 1420
        assert layout.y == FRAME_H - 270 - MARGIN  # 790

    def test_top_left(self):
        layout = get_pip_layout(PipPreset.top_left, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.width == 480
        assert layout.height == 270
        assert layout.x == MARGIN
        assert layout.y == MARGIN

    def test_top_right(self):
        layout = get_pip_layout(PipPreset.top_right, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == FRAME_W - 480 - MARGIN
        assert layout.y == MARGIN

    def test_bottom_left(self):
        layout = get_pip_layout(PipPreset.bottom_left, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == MARGIN
        assert layout.y == FRAME_H - 270 - MARGIN

    def test_center(self):
        layout = get_pip_layout(PipPreset.center, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == (FRAME_W - 480) // 2
        assert layout.y == (FRAME_H - 270) // 2

    def test_custom_raises_without_override(self):
        """Custom preset requires caller to build PipLayout manually."""
        with pytest.raises(ValueError, match="custom"):
            get_pip_layout(PipPreset.custom, FRAME_W, FRAME_H)

    def test_scale_half(self):
        layout = get_pip_layout(PipPreset.bottom_right, FRAME_W, FRAME_H, pip_scale=0.5)
        assert layout.width == 960
        assert layout.height == 540

    def test_4k_frame(self):
        layout = get_pip_layout(PipPreset.bottom_right, 3840, 2160, pip_scale=0.25)
        assert layout.width == 960
        assert layout.height == 540


class TestApplyPip:
    def _make_project(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        return KdenliveProject.model_validate({
            "profile": {"width": 1920, "height": 1080, "colorspace": "709"},
            "tracks": [{"id": "0"}, {"id": "1"}],
        })

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_apply_pip_calls_patch(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)
        layout = PipLayout(x=1420, y=790, width=480, height=270)

        result = apply_pip(project, overlay_track=1, base_track=0, start_frame=0, end_frame=150, layout=layout)

        mock_patch.assert_called_once()
        intents = mock_patch.call_args[0][1]
        assert len(intents) == 1
        intent = intents[0]
        # Post-rewire: apply_pip delegates to apply_composite with blend_mode="cairoblend".
        assert intent.composition_type == "frei0r.cairoblend"
        assert intent.params["geometry"] == "1420/790:480x270:100"
        assert intent.params["1"] == "normal"

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_apply_pip_deep_copies(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)
        layout = PipLayout(x=0, y=0, width=480, height=270)

        result = apply_pip(project, overlay_track=1, base_track=0, start_frame=0, end_frame=150, layout=layout)
        assert result is not project


class TestApplyWipe:
    def _make_project(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        return KdenliveProject.model_validate({
            "profile": {"width": 1920, "height": 1080, "colorspace": "709"},
            "tracks": [{"id": "0"}, {"id": "1"}],
        })

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_dissolve(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)

        result = apply_wipe(project, track_a=0, track_b=1, start_frame=100, end_frame=130, wipe_type="dissolve")

        intent = mock_patch.call_args[0][1][0]
        assert intent.composition_type == "luma"
        assert "resource" not in intent.params or intent.params["resource"] == ""

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_wipe_luma(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)

        result = apply_wipe(project, track_a=0, track_b=1, start_frame=100, end_frame=130, wipe_type="wipe")

        intent = mock_patch.call_args[0][1][0]
        assert intent.composition_type == "luma"
        assert intent.params.get("resource") != ""

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_invalid_wipe_type(self, mock_patch):
        project = self._make_project()
        with pytest.raises(ValueError, match="wipe_type"):
            apply_wipe(project, track_a=0, track_b=1, start_frame=0, end_frame=30, wipe_type="unknown")
