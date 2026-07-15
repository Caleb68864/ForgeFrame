"""Unit tests for the two-pass loudnorm pipeline + audio_normalize_two_pass tool.

Covers pass-2 filter/param assembly (incl. measured values), output naming,
pass-2 JSON parsing, orchestration (measurement reuse, video remux, linear ->
dynamic fallback warning), and MCP tool registration. No FFmpeg execution --
``run_ffmpeg``, ``measure_loudness``, ``_measure_thresh`` and ``_has_video_stream``
are mocked.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import LoudnessResult
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult
from workshop_video_brain.edit_mcp.pipelines import loudnorm_two_pass as ln

_PIPE = "workshop_video_brain.edit_mcp.pipelines.loudnorm_two_pass"


def _result(success: bool = True, stderr: str = "") -> FFmpegResult:
    return FFmpegResult(
        success=success,
        input_path="/in.wav",
        output_path="/out.wav",
        command=["ffmpeg"],
        stdout="",
        stderr=stderr,
        duration_ms=1.0,
    )


# Realistic loudnorm pass-2 JSON blocks (as emitted on FFmpeg stderr).
_JSON_DYNAMIC = """
    {
        "input_i" : "-33.75",
        "input_tp" : "-30.06",
        "input_lra" : "0.00",
        "input_thresh" : "-43.75",
        "output_i" : "-15.95",
        "output_tp" : "-12.18",
        "output_lra" : "0.10",
        "output_thresh" : "-25.95",
        "normalization_type" : "dynamic",
        "target_offset" : "-0.05"
    }
"""
_JSON_LINEAR = _JSON_DYNAMIC.replace('"dynamic"', '"linear"').replace(
    '"-15.95"', '"-16.00"'
)


from tests._testkit import call_tool as _invoke  # noqa: E402
from tests._testkit import registered_tool_names as _tool_names  # noqa: E402


# ---------------------------------------------------------------------------
# Filter / param assembly
# ---------------------------------------------------------------------------

class TestBuildPass2Filter:
    def test_exact_two_pass_form(self):
        f = ln.build_loudnorm_pass2_filter(
            target_i=-16.0, target_tp=-1.5, target_lra=11.0,
            measured_i=-21.3, measured_tp=-4.1, measured_lra=9.2,
            measured_thresh=-31.7, linear=True,
        )
        assert f.startswith("loudnorm=")
        assert "I=-16.0" in f
        assert "TP=-1.5" in f
        assert "LRA=11.0" in f
        assert "measured_I=-21.3" in f
        assert "measured_TP=-4.1" in f
        assert "measured_LRA=9.2" in f
        assert "measured_thresh=-31.7" in f
        assert "linear=true" in f
        assert "print_format=json" in f

    def test_linear_false_literal(self):
        f = ln.build_loudnorm_pass2_filter(
            -16.0, -1.5, 11.0, -21.3, -4.1, 9.2, -31.7, linear=False,
        )
        assert "linear=false" in f

    def test_measured_values_are_present_and_ordered(self):
        f = ln.build_loudnorm_pass2_filter(
            -14.0, -2.0, 7.0, -20.0, -5.0, 8.0, -30.0,
        )
        # target block precedes measured block
        assert f.index("I=-14.0") < f.index("measured_I=-20.0")
        assert f.index("measured_I=-20.0") < f.index("measured_thresh=-30.0")


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------

class TestOutputNaming:
    def test_default_suffix(self):
        out = ln.normalized_output_path(
            Path("/w/media/raw/take.wav"), Path("/w/media/processed")
        )
        assert out == Path("/w/media/processed/take_normalized.wav")

    def test_custom_name_inherits_source_suffix(self):
        out = ln.normalized_output_path(
            Path("/w/media/raw/take.mp4"), Path("/w/media/processed"), "loud"
        )
        assert out == Path("/w/media/processed/loud.mp4")

    def test_custom_name_with_extension_kept(self):
        out = ln.normalized_output_path(
            Path("/w/media/raw/take.wav"), Path("/w/media/processed"), "loud.flac"
        )
        assert out == Path("/w/media/processed/loud.flac")


# ---------------------------------------------------------------------------
# Pass-2 JSON parsing
# ---------------------------------------------------------------------------

class TestParsePass2:
    def test_parses_dynamic(self):
        p = ln.parse_pass2_result(_JSON_DYNAMIC)
        assert p["normalization_type"] == "dynamic"
        assert p["output_i"] == -15.95

    def test_parses_linear(self):
        p = ln.parse_pass2_result(_JSON_LINEAR)
        assert p["normalization_type"] == "linear"
        assert p["output_i"] == -16.0

    def test_missing_json_returns_nones(self):
        p = ln.parse_pass2_result("no json here")
        assert p["normalization_type"] is None
        assert p["output_i"] is None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class TestNormalizeTwoPassFile:
    def _patches(self, has_video=False, apply_ok=True, stderr=_JSON_DYNAMIC):
        return (
            patch(f"{_PIPE}._has_video_stream", return_value=has_video),
            patch(
                f"{_PIPE}.measure_loudness",
                return_value=LoudnessResult(
                    input_i=-33.75, input_tp=-30.06, input_lra=0.0
                ),
            ),
            patch(f"{_PIPE}._measure_thresh", return_value=-43.75),
            patch(f"{_PIPE}.run_ffmpeg", return_value=_result(apply_ok, stderr)),
        )

    def test_audio_only_no_video_copy_arg(self):
        pv, pm, pt, pr = self._patches(has_video=False)
        with pv, pm, pt, pr as mock_run:
            res = ln.normalize_two_pass_file(Path("/in.wav"), Path("/out.wav"))
        assert res["success"] is True
        assert res["has_video"] is False
        ffmpeg_args = mock_run.call_args[0][0]
        assert "-c:v" not in ffmpeg_args
        assert "-af" in ffmpeg_args
        af = ffmpeg_args[ffmpeg_args.index("-af") + 1]
        # measured values from mocks are threaded into the filter
        assert "measured_I=-33.75" in af
        assert "measured_thresh=-43.75" in af

    def test_video_source_stream_copies_video(self):
        pv, pm, pt, pr = self._patches(has_video=True)
        with pv, pm, pt, pr as mock_run:
            res = ln.normalize_two_pass_file(Path("/in.mp4"), Path("/out.mp4"))
        assert res["has_video"] is True
        ffmpeg_args = mock_run.call_args[0][0]
        assert ffmpeg_args[:2] == ["-c:v", "copy"]

    def test_reports_measured_and_target(self):
        pv, pm, pt, pr = self._patches()
        with pv, pm, pt, pr:
            res = ln.normalize_two_pass_file(
                Path("/in.wav"), Path("/out.wav"),
                target_i=-14.0, target_tp=-2.0, target_lra=7.0,
            )
        assert res["measured"] == {
            "i": -33.75, "tp": -30.06, "lra": 0.0, "thresh": -43.75,
        }
        assert res["target"] == {"i": -14.0, "tp": -2.0, "lra": 7.0}
        assert res["achieved_i"] == -15.95

    def test_linear_requested_dynamic_applied_yields_warning(self):
        pv, pm, pt, pr = self._patches(stderr=_JSON_DYNAMIC)
        with pv, pm, pt, pr:
            res = ln.normalize_two_pass_file(Path("/in.wav"), Path("/out.wav"))
        assert res["linear_requested"] is True
        assert res["linear_applied"] is False
        assert res["normalization_type"] == "dynamic"
        assert res["warning"] is not None
        assert "linear" in res["warning"].lower()

    def test_linear_applied_no_warning(self):
        pv, pm, pt, pr = self._patches(stderr=_JSON_LINEAR)
        with pv, pm, pt, pr:
            res = ln.normalize_two_pass_file(Path("/in.wav"), Path("/out.wav"))
        assert res["linear_applied"] is True
        assert res["warning"] is None

    def test_measurement_failure_aborts(self):
        with patch(f"{_PIPE}._has_video_stream", return_value=False), \
             patch(f"{_PIPE}.measure_loudness", return_value=None), \
             patch(f"{_PIPE}.run_ffmpeg") as mock_run:
            res = ln.normalize_two_pass_file(Path("/in.wav"), Path("/out.wav"))
        assert res["success"] is False
        assert "measurement failed" in res["error"].lower()
        mock_run.assert_not_called()

    def test_apply_failure_surfaces_error(self):
        pv, pm, pt, pr = self._patches(apply_ok=False, stderr="boom")
        with pv, pm, pt, pr:
            res = ln.normalize_two_pass_file(Path("/in.wav"), Path("/out.wav"))
        assert res["success"] is False
        assert res["final_output"] is None
        assert "loudnorm apply failed" in res["error"].lower()

    def test_dry_run_builds_command_without_measuring(self):
        with patch(f"{_PIPE}._has_video_stream", return_value=False), \
             patch(f"{_PIPE}.measure_loudness") as mock_measure:
            res = ln.normalize_two_pass_file(
                Path("/in.wav"), Path("/out.wav"), dry_run=True
            )
        assert res["success"] is True
        assert len(res["steps"]) == 1
        mock_measure.assert_not_called()


# ---------------------------------------------------------------------------
# MCP tool: audio_normalize_two_pass
# ---------------------------------------------------------------------------

class TestAudioNormalizeTwoPassTool:
    def _ws(self, tmp_path: Path) -> Path:
        (tmp_path / "media" / "raw").mkdir(parents=True)
        return tmp_path

    def test_registered_in_mcp(self):
        from workshop_video_brain.server import mcp
        assert "audio_normalize_two_pass" in _tool_names(mcp)

    def test_errors_when_no_media(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.audio_normalize_two_pass import (  # noqa: E501
            audio_normalize_two_pass,
        )
        ws = self._ws(tmp_path)
        res = _invoke(audio_normalize_two_pass, str(ws))
        assert res["status"] == "error"
        assert "No media" in res["message"]

    def test_writes_to_processed_and_reports_values(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import (
            audio_normalize_two_pass as bundle,
        )
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "take.wav"
        src.write_bytes(b"\x00")

        def fake(input_path, output_path, **kwargs):
            Path(output_path).write_bytes(b"\x00")
            return {
                "success": True,
                "measured": {"i": -30.0, "tp": -25.0, "lra": 5.0, "thresh": -40.0},
                "target": {"i": -16.0, "tp": -1.5, "lra": 11.0},
                "normalization_type": "dynamic",
                "linear_requested": True,
                "linear_applied": False,
                "achieved_i": -16.1,
                "has_video": False,
                "warning": "fell back to dynamic",
                "steps": [{}],
                "final_output": str(output_path),
            }

        with patch.object(bundle, "normalize_two_pass_file", side_effect=fake):
            res = _invoke(
                bundle.audio_normalize_two_pass, str(ws),
                source="media/raw/take.wav",
            )
        assert res["status"] == "success"
        data = res["data"]
        assert data["output"].endswith("media/processed/take_normalized.wav")
        assert Path(data["output"]).exists()
        assert data["measured"]["thresh"] == -40.0
        assert data["target"]["i"] == -16.0
        assert data["achieved_i"] == -16.1
        assert data["warning"] == "fell back to dynamic"

    def test_refuses_to_overwrite_raw_source(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles import (
            audio_normalize_two_pass as bundle,
        )
        ws = self._ws(tmp_path)
        src = ws / "media" / "raw" / "take.wav"
        src.write_bytes(b"\x00")
        with patch.object(bundle, "normalize_two_pass_file") as mock_norm:
            res = _invoke(
                bundle.audio_normalize_two_pass, str(ws),
                source="media/raw/take.wav",
                output_name="../raw/take.wav",
            )
        assert res["status"] == "error"
        assert "raw" in res["message"].lower()
        mock_norm.assert_not_called()
