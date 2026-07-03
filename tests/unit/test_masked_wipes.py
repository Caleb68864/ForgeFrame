"""Unit tests for the masked / custom-luma wipe pipeline.

Covers the three pure functions in ``pipelines/masked_wipes.py``:
``resolve_luma``, ``apply_masked_wipe``, ``apply_luma_key``.
"""
from __future__ import annotations

import os
from copy import deepcopy
from unittest.mock import patch

import pytest

from workshop_video_brain.edit_mcp.pipelines.masked_wipes import (
    LUMA_DIR,
    LUMAKEY_SERVICE,
    apply_luma_key,
    apply_masked_wipe,
    resolve_luma,
)


def _make_project():
    from workshop_video_brain.core.models.kdenlive import KdenliveProject
    return KdenliveProject.model_validate({
        "profile": {"width": 1920, "height": 1080, "colorspace": "709"},
        "tracks": [{"id": "0"}, {"id": "1"}],
    })


class TestResolveLuma:
    def test_bare_name_resolves_under_hd_dir(self):
        assert resolve_luma("luma03") == os.path.join(LUMA_DIR, "luma03.pgm")

    def test_bare_name_with_extension_kept(self):
        assert resolve_luma("luma07.pgm") == os.path.join(LUMA_DIR, "luma07.pgm")

    def test_absolute_user_path_verbatim(self):
        p = "/home/user/mattes/gradient.png"
        assert resolve_luma(p) == p

    def test_relative_path_with_sep_verbatim(self):
        p = "mattes/wipe.pgm"
        assert resolve_luma(p) == p

    def test_tilde_expanded(self):
        result = resolve_luma("~/mattes/wipe.pgm")
        assert result == os.path.expanduser("~/mattes/wipe.pgm")
        assert "~" not in result

    def test_existing_bare_file_used_verbatim(self, tmp_path, monkeypatch):
        matte = tmp_path / "custom.pgm"
        matte.write_text("P2\n")
        monkeypatch.chdir(tmp_path)
        assert resolve_luma("custom.pgm") == "custom.pgm"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="luma_file"):
            resolve_luma("   ")


class TestApplyMaskedWipe:
    @patch("workshop_video_brain.edit_mcp.pipelines.masked_wipes.patch_project")
    def test_builtin_name(self, mock_patch):
        project = _make_project()
        mock_patch.return_value = deepcopy(project)

        apply_masked_wipe(
            project, track_a=0, track_b=1, start_frame=100, end_frame=130,
            luma_file="luma05",
        )

        intent = mock_patch.call_args[0][1][0]
        assert intent.composition_type == "luma"
        assert intent.params["resource"] == os.path.join(LUMA_DIR, "luma05.pgm")
        assert intent.params["invert"] == "0"
        assert intent.params["softness"] == "0.0"
        assert intent.start_frame == 100
        assert intent.end_frame == 130

    @patch("workshop_video_brain.edit_mcp.pipelines.masked_wipes.patch_project")
    def test_custom_matte_invert_softness(self, mock_patch):
        project = _make_project()
        mock_patch.return_value = deepcopy(project)

        apply_masked_wipe(
            project, track_a=1, track_b=2, start_frame=0, end_frame=48,
            luma_file="/mattes/heart.png", invert=True, softness=0.35,
        )

        intent = mock_patch.call_args[0][1][0]
        assert intent.params["resource"] == "/mattes/heart.png"
        assert intent.params["invert"] == "1"
        assert intent.params["softness"] == "0.35"

    @patch("workshop_video_brain.edit_mcp.pipelines.masked_wipes.patch_project")
    def test_deep_copies(self, mock_patch):
        project = _make_project()
        mock_patch.return_value = deepcopy(project)
        result = apply_masked_wipe(
            project, track_a=0, track_b=1, start_frame=0, end_frame=30,
            luma_file="luma01",
        )
        assert result is not project

    def test_same_track_raises(self):
        with pytest.raises(ValueError, match="different tracks"):
            apply_masked_wipe(
                _make_project(), track_a=1, track_b=1,
                start_frame=0, end_frame=30, luma_file="luma01",
            )

    def test_bad_frames_raises(self):
        with pytest.raises(ValueError, match="greater than"):
            apply_masked_wipe(
                _make_project(), track_a=0, track_b=1,
                start_frame=30, end_frame=30, luma_file="luma01",
            )

    def test_softness_out_of_range_raises(self):
        with pytest.raises(ValueError, match="softness"):
            apply_masked_wipe(
                _make_project(), track_a=0, track_b=1,
                start_frame=0, end_frame=30, luma_file="luma01", softness=1.5,
            )

    def test_empty_luma_raises(self):
        with pytest.raises(ValueError, match="luma_file"):
            apply_masked_wipe(
                _make_project(), track_a=0, track_b=1,
                start_frame=0, end_frame=30, luma_file="",
            )


class TestApplyLumaKey:
    @patch("workshop_video_brain.edit_mcp.pipelines.effect_apply._patcher.patch_project")
    def test_adds_lumakey_filter(self, mock_patch):
        project = _make_project()
        mock_patch.return_value = deepcopy(project)

        apply_luma_key(project, track_index=2, clip_index=0,
                       threshold=0.2, tolerance=0.1, softness=0.05)

        intent = mock_patch.call_args[0][1][0]
        assert intent.effect_name == LUMAKEY_SERVICE
        assert intent.track_index == 2
        assert intent.clip_index == 0
        assert intent.params == {
            "av.threshold": "0.2",
            "av.tolerance": "0.1",
            "av.softness": "0.05",
        }

    def test_threshold_out_of_range_raises(self):
        with pytest.raises(ValueError, match="threshold"):
            apply_luma_key(_make_project(), 0, 0, threshold=2.0)

    def test_tolerance_out_of_range_raises(self):
        with pytest.raises(ValueError, match="tolerance"):
            apply_luma_key(_make_project(), 0, 0, tolerance=-0.1)

    def test_softness_out_of_range_raises(self):
        with pytest.raises(ValueError, match="softness"):
            apply_luma_key(_make_project(), 0, 0, softness=5.0)
