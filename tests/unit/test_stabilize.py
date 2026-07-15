"""Unit tests for the video stabilization pipeline + media_stabilize tool.

Covers command construction, parameter clamping, output naming, the
vidstab -> deshake fallback selection, and MCP tool registration. No FFmpeg
execution -- ``run_ffmpeg`` and the availability probe are mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult
from workshop_video_brain.edit_mcp.pipelines import stabilize

_PIPE = "workshop_video_brain.edit_mcp.pipelines.stabilize"


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
# Parameter clamping
# ---------------------------------------------------------------------------

class TestClampParams:
    def test_defaults_pass_through(self):
        assert stabilize.clamp_params() == {
            "shakiness": 5,
            "smoothing": 15,
            "accuracy": 15,
            "zoom": 0,
        }

    def test_upper_bounds(self):
        p = stabilize.clamp_params(shakiness=99, smoothing=9999, accuracy=99, zoom=9999)
        assert p == {"shakiness": 10, "smoothing": 100, "accuracy": 15, "zoom": 100}

    def test_lower_bounds(self):
        p = stabilize.clamp_params(shakiness=-3, smoothing=-3, accuracy=0, zoom=-9999)
        assert p == {"shakiness": 1, "smoothing": 0, "accuracy": 1, "zoom": -100}


# ---------------------------------------------------------------------------
# Filter-string construction
# ---------------------------------------------------------------------------

class TestFilterConstruction:
    def test_detect_filter_has_result_path_and_clamps(self):
        f = stabilize.build_detect_filter(Path("/tmp/x.trf"), shakiness=50, accuracy=1)
        assert f.startswith("vidstabdetect=")
        assert "shakiness=10" in f  # clamped from 50
        assert "accuracy=1" in f
        assert "result=/tmp/x.trf" in f

    def test_transform_filter_reads_trf_and_unsharp(self):
        f = stabilize.build_transform_filter(Path("/tmp/x.trf"), smoothing=15, zoom=5)
        assert "vidstabtransform=" in f
        assert "input=/tmp/x.trf" in f
        assert "smoothing=15" in f
        assert "zoom=5" in f
        assert "unsharp=5:5:0.8" in f

    def test_deshake_filter(self):
        assert stabilize.build_deshake_filter() == "deshake=edge=1"


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------

class TestOutputNaming:
    def test_default_suffix(self):
        out = stabilize.stabilized_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed")
        )
        assert out == Path("/w/media/processed/clip_stabilized.mov")

    def test_custom_name_without_extension_inherits_source_suffix(self):
        out = stabilize.stabilized_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed"), "steady"
        )
        assert out == Path("/w/media/processed/steady.mov")

    def test_custom_name_with_extension_kept(self):
        out = stabilize.stabilized_output_path(
            Path("/w/media/raw/clip.mov"), Path("/w/media/processed"), "steady.mp4"
        )
        assert out == Path("/w/media/processed/steady.mp4")


# ---------------------------------------------------------------------------
# stabilize_file orchestration
# ---------------------------------------------------------------------------

class TestStabilizeFile:
    def test_vidstab_two_pass_when_available(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            res = stabilize.stabilize_file(Path("/in.mp4"), Path("/out.mp4"))
        assert res["success"] is True
        assert res["method"] == "vidstab"
        assert mock_run.call_count == 2  # detect + transform
        assert len(res["steps"]) == 2

    def test_pass1_detect_writes_trf_and_null_output(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            stabilize.stabilize_file(Path("/in.mp4"), Path("/out.mp4"))
        # First call = detect pass
        args, kwargs = mock_run.call_args_list[0]
        ffmpeg_args = args[0]
        assert "-vf" in ffmpeg_args
        vf = ffmpeg_args[ffmpeg_args.index("-vf") + 1]
        assert "vidstabdetect" in vf
        assert ".trf" in vf
        assert "-f" in ffmpeg_args and "null" in ffmpeg_args
        assert str(kwargs["output_path"]) in ("/dev/null",)

    def test_pass2_transform_encodes_to_output(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            stabilize.stabilize_file(Path("/in.mp4"), Path("/out.mp4"))
        args, kwargs = mock_run.call_args_list[1]
        ffmpeg_args = args[0]
        vf = ffmpeg_args[ffmpeg_args.index("-vf") + 1]
        assert "vidstabtransform" in vf
        assert "libx264" in ffmpeg_args
        assert "-c:a" in ffmpeg_args  # audio copied through
        assert str(kwargs["output_path"]) == "/out.mp4"

    def test_deshake_fallback_when_unavailable(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=False), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            res = stabilize.stabilize_file(Path("/in.mp4"), Path("/out.mp4"))
        assert res["method"] == "deshake"
        assert mock_run.call_count == 1  # single pass
        vf = mock_run.call_args[0][0]
        assert "deshake" in vf[vf.index("-vf") + 1]

    def test_force_deshake_overrides_available_vidstab(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)) as mock_run:
            res = stabilize.stabilize_file(
                Path("/in.mp4"), Path("/out.mp4"), force_deshake=True
            )
        assert res["method"] == "deshake"
        assert mock_run.call_count == 1

    def test_pass1_failure_aborts_before_pass2(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(False)) as mock_run:
            res = stabilize.stabilize_file(Path("/in.mp4"), Path("/out.mp4"))
        assert res["success"] is False
        assert mock_run.call_count == 1  # never reached pass 2
        assert res["final_output"] is None
        assert "pass 1" in res["error"]

    def test_dry_run_returns_commands_without_execution(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True):
            res = stabilize.stabilize_file(
                Path("/in.mp4"), Path("/out.mp4"), dry_run=True
            )
        assert res["success"] is True
        assert res["method"] == "vidstab"
        assert len(res["steps"]) == 2

    def test_clamped_params_reported(self):
        with patch(f"{_PIPE}.vidstab_available", return_value=True), \
             patch(f"{_PIPE}.run_ffmpeg", return_value=_result(True)):
            res = stabilize.stabilize_file(
                Path("/in.mp4"), Path("/out.mp4"), shakiness=99, smoothing=-1
            )
        assert res["params"]["shakiness"] == 10
        assert res["params"]["smoothing"] == 0


# ---------------------------------------------------------------------------
# MCP tool: media_stabilize
# ---------------------------------------------------------------------------

class TestMediaStabilizeTool:
    def _ws(self, tmp_path: Path) -> Path:
        (tmp_path / "media" / "raw").mkdir(parents=True)
        return tmp_path

    def test_registered_in_mcp(self):
        from workshop_video_brain.server import mcp
        assert "media_stabilize" in _tool_names(mcp)

    def test_errors_when_no_video(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.stabilize import media_stabilize
        ws = self._ws(tmp_path)
        res = _invoke(media_stabilize, str(ws))
        assert res["status"] == "error"
        assert "No video" in res["message"]

    def test_writes_to_processed_and_reports_method(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import stabilize as bundle
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "clip.mp4"
        src.write_bytes(b"\x00")

        def fake_stabilize(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"\x00")
            return {
                "success": True,
                "method": "vidstab",
                "steps": [{}, {}],
                "final_output": str(output_path),
                "params": stabilize.clamp_params(**kwargs) if kwargs else {},
            }

        with patch.object(bundle, "stabilize_file", side_effect=fake_stabilize):
            res = _invoke(bundle.media_stabilize, str(ws), source="media/raw/clip.mp4")
        assert res["status"] == "success"
        data = res["data"]
        assert data["method"] == "vidstab"
        assert data["output"].endswith("media/processed/clip_stabilized.mp4")
        assert Path(data["output"]).exists()

    def test_deshake_note_surfaced(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import stabilize as bundle
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "clip.mp4"
        src.write_bytes(b"\x00")

        def fake_stabilize(input_path, output_path, **kwargs):
            return {
                "success": True,
                "method": "deshake",
                "steps": [{}],
                "final_output": str(output_path),
                "params": {},
            }

        with patch.object(bundle, "stabilize_file", side_effect=fake_stabilize):
            res = _invoke(bundle.media_stabilize, str(ws), source="media/raw/clip.mp4")
        assert res["status"] == "success"
        assert "deshake" in res["data"]["note"]

    def test_refuses_to_overwrite_raw_source(self, tmp_path):
        # output_name resolving back onto the raw source is rejected.
        from workshop_video_brain.edit_mcp.server.bundles import stabilize as bundle
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "clip.mp4"
        src.write_bytes(b"\x00")
        # Point processed output back at raw via an absolute traversal name.
        with patch.object(bundle, "stabilize_file") as mock_stab:
            res = _invoke(bundle.media_stabilize, 
                str(ws),
                source="media/raw/clip.mp4",
                output_name="../raw/clip.mp4",
            )
        assert res["status"] == "error"
        assert "raw" in res["message"].lower()
        mock_stab.assert_not_called()
