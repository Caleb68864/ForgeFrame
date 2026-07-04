"""Unit tests for the video denoise pipeline + media_denoise_video tool.

Covers preset mapping, filter construction, method dispatch, output naming,
audio-copy command construction, and MCP tool registration. No FFmpeg
execution -- ``run_ffmpeg`` is mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult
from workshop_video_brain.edit_mcp.pipelines import denoise_video as dn

_PIPE = "workshop_video_brain.edit_mcp.pipelines.denoise_video"


def _result(success: bool = True) -> FFmpegResult:
    return FFmpegResult(
        success=success,
        input_path="/in.mp4",
        output_path="/out.mp4",
        command=["ffmpeg"],
        stdout="",
        stderr="" if success else "boom",
        duration_ms=1.0,
    )


from tests._testkit import call_tool as _invoke  # noqa: E402
from tests._testkit import registered_tool_names as _tool_names  # noqa: E402


# ---------------------------------------------------------------------------
# Preset mapping / filter construction
# ---------------------------------------------------------------------------

class TestHqdn3dPresets:
    def test_medium_is_ffmpeg_default(self):
        assert dn.build_hqdn3d_filter("medium") == "hqdn3d=4.0:3.0:6.0:4.5"

    def test_light_and_strong_scale(self):
        assert dn.build_hqdn3d_filter("light") == "hqdn3d=2.0:1.5:3.0:2.25"
        assert dn.build_hqdn3d_filter("strong") == "hqdn3d=8.0:6.0:12.0:9.0"

    def test_unknown_strength_defaults_medium(self):
        assert dn.build_hqdn3d_filter("bogus") == dn.build_hqdn3d_filter("medium")

    def test_strong_is_stronger_than_light(self):
        # numeric check: strong luma_spatial > light luma_spatial
        light = dn._HQDN3D_PRESETS["light"][0]
        strong = dn._HQDN3D_PRESETS["strong"][0]
        assert strong > light


class TestAtadenoisePresets:
    def test_filter_form(self):
        assert dn.build_atadenoise_filter("medium") == "atadenoise=0a=0.02:0b=0.04"

    def test_light_lower_thresholds(self):
        assert dn.build_atadenoise_filter("light") == "atadenoise=0a=0.01:0b=0.02"


class TestMethodDispatch:
    def test_default_method_is_hqdn3d(self):
        assert dn.build_denoise_filter("medium", "hqdn3d").startswith("hqdn3d=")

    def test_atadenoise_selected(self):
        assert dn.build_denoise_filter("medium", "atadenoise").startswith(
            "atadenoise="
        )

    def test_unknown_method_defaults_hqdn3d(self):
        assert dn.build_denoise_filter("medium", "bogus").startswith("hqdn3d=")

    def test_params_report(self):
        p = dn.denoise_params("strong", "hqdn3d")
        assert p["strength"] == "strong"
        assert p["method"] == "hqdn3d"
        assert p["filter"] == "hqdn3d=8.0:6.0:12.0:9.0"
        assert p["values"] == [8.0, 6.0, 12.0, 9.0]


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------

class TestOutputNaming:
    def test_default_suffix(self):
        out = dn.denoised_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed")
        )
        assert out == Path("/w/media/processed/clip_denoised.mov")

    def test_custom_name_inherits_suffix(self):
        out = dn.denoised_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed"), "clean"
        )
        assert out == Path("/w/media/processed/clean.mov")

    def test_custom_name_with_extension_kept(self):
        out = dn.denoised_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed"), "clean.mp4"
        )
        assert out == Path("/w/media/processed/clean.mp4")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class TestDenoiseVideoFile:
    def test_builds_vf_and_copies_audio(self):
        with patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            res = dn.denoise_video_file(
                Path("/in.mp4"), Path("/out.mp4"), strength="strong"
            )
        assert res["success"] is True
        assert res["method"] == "hqdn3d"
        assert res["strength"] == "strong"
        args = mock_run.call_args[0][0]
        assert "-vf" in args
        vf = args[args.index("-vf") + 1]
        assert vf == "hqdn3d=8.0:6.0:12.0:9.0"
        assert "libx264" in args
        # audio stream-copied
        assert "-c:a" in args
        assert args[args.index("-c:a") + 1] == "copy"

    def test_atadenoise_path(self):
        with patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            res = dn.denoise_video_file(
                Path("/in.mp4"), Path("/out.mp4"), method="atadenoise"
            )
        assert res["method"] == "atadenoise"
        vf = mock_run.call_args[0][0]
        assert "atadenoise" in vf[vf.index("-vf") + 1]

    def test_failure_surfaces_error(self):
        with patch(f"{_PIPE}.run_ffmpeg", return_value=_result(False)):
            res = dn.denoise_video_file(Path("/in.mp4"), Path("/out.mp4"))
        assert res["success"] is False
        assert res["final_output"] is None
        assert "denoise failed" in res["error"].lower()

    def test_dry_run(self):
        res = dn.denoise_video_file(
            Path("/in.mp4"), Path("/out.mp4"), dry_run=True
        )
        assert res["success"] is True
        assert res["final_output"] == "/out.mp4"


# ---------------------------------------------------------------------------
# MCP tool: media_denoise_video
# ---------------------------------------------------------------------------

class TestMediaDenoiseVideoTool:
    def _ws(self, tmp_path: Path) -> Path:
        (tmp_path / "media" / "raw").mkdir(parents=True)
        return tmp_path

    def test_registered_in_mcp(self):
        from workshop_video_brain.server import mcp
        assert "media_denoise_video" in _tool_names(mcp)

    def test_errors_when_no_video(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.media_denoise_video import (  # noqa: E501
            media_denoise_video,
        )
        ws = self._ws(tmp_path)
        res = _invoke(media_denoise_video, str(ws))
        assert res["status"] == "error"
        assert "No video" in res["message"]

    def test_writes_to_processed_and_reports_settings(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import (
            media_denoise_video as bundle,
        )
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "clip.mp4"
        src.write_bytes(b"\x00")

        def fake(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"\x00")
            return {
                "success": True,
                "method": "hqdn3d",
                "strength": "medium",
                "filter": "hqdn3d=4.0:3.0:6.0:4.5",
                "params": {"values": [4.0, 3.0, 6.0, 4.5]},
                "steps": [{}],
                "final_output": str(output_path),
            }

        with patch.object(bundle, "denoise_video_file", side_effect=fake):
            res = _invoke(
                bundle.media_denoise_video, str(ws), source="media/raw/clip.mp4"
            )
        assert res["status"] == "success"
        data = res["data"]
        assert data["output"].endswith("media/processed/clip_denoised.mp4")
        assert Path(data["output"]).exists()
        assert data["method"] == "hqdn3d"
        assert data["settings"] == [4.0, 3.0, 6.0, 4.5]

    def test_refuses_to_overwrite_raw_source(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import (
            media_denoise_video as bundle,
        )
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "clip.mp4"
        src.write_bytes(b"\x00")
        with patch.object(bundle, "denoise_video_file") as mock_dn:
            res = _invoke(
                bundle.media_denoise_video, str(ws),
                source="media/raw/clip.mp4",
                output_name="../raw/clip.mp4",
            )
        assert res["status"] == "error"
        assert "raw" in res["message"].lower()
        mock_dn.assert_not_called()
