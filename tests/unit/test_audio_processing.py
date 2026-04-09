"""Unit tests for the FFmpeg audio processing toolkit."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult, run_ffmpeg

# Module paths for patching
_RUNNER_SUBPROCESS = "workshop_video_brain.edit_mcp.adapters.ffmpeg.runner.subprocess.run"
_AUDIO_RUN_FFMPEG = "workshop_video_brain.edit_mcp.adapters.ffmpeg.audio.run_ffmpeg"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ffmpeg_result(success: bool = True, **kwargs) -> FFmpegResult:
    return FFmpegResult(
        success=success,
        input_path="/in.wav",
        output_path="/out.wav",
        command=["ffmpeg", "-y", "-i", "/in.wav", "/out.wav"],
        stdout="",
        stderr="" if success else "error: something went wrong",
        duration_ms=50.0,
        **kwargs,
    )


def _make_proc_result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# FFmpeg runner tests
# ---------------------------------------------------------------------------

class TestRunFFmpeg:
    def test_builds_correct_command(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()) as mock_run:
            result = run_ffmpeg(["-af", "loudnorm=I=-16"], inp, out)
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-i" in cmd
        assert str(inp) in cmd
        assert str(out) in cmd
        assert "-af" in cmd
        assert "loudnorm=I=-16" in cmd

    def test_overwrite_adds_y_flag(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()) as mock_run:
            run_ffmpeg([], inp, out, overwrite=True)
        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd

    def test_no_overwrite_omits_y_flag(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()) as mock_run:
            run_ffmpeg([], inp, out, overwrite=False)
        cmd = mock_run.call_args[0][0]
        assert "-y" not in cmd

    def test_dry_run_returns_command_without_executing(self, tmp_path):
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS) as mock_run:
            result = run_ffmpeg(["-af", "loudnorm"], inp, out, dry_run=True)
        mock_run.assert_not_called()
        assert result.success is True
        assert "ffmpeg" in result.command
        assert "-af" in result.command
        assert "loudnorm" in result.command

    def test_failed_subprocess_returns_success_false(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result(returncode=1, stderr="fatal error")):
            result = run_ffmpeg([], inp, out)
        assert result.success is False
        assert "fatal error" in result.stderr

    def test_result_contains_input_output_paths(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()):
            result = run_ffmpeg([], inp, out)
        assert result.input_path == str(inp)
        assert result.output_path == str(out)

    def test_result_captures_stdout_stderr(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result(stdout="out", stderr="err")):
            result = run_ffmpeg([], inp, out)
        assert result.stdout == "out"
        assert result.stderr == "err"

    def test_result_has_duration_ms(self, tmp_path):
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()):
            result = run_ffmpeg([], inp, out)
        assert result.duration_ms >= 0.0

    def test_command_order_y_before_i(self, tmp_path):
        """ffmpeg -y must come before -i."""
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with patch(_RUNNER_SUBPROCESS, return_value=_make_proc_result()) as mock_run:
            run_ffmpeg([], inp, out, overwrite=True)
        cmd = mock_run.call_args[0][0]
        assert cmd.index("-y") < cmd.index("-i")


# ---------------------------------------------------------------------------
# Individual audio tool tests (mock run_ffmpeg)
# ---------------------------------------------------------------------------

class TestNormalizeAudio:
    def test_passes_loudnorm_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import normalize_audio
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            normalize_audio(inp, out, target_lufs=-16.0, true_peak=-1.5, loudness_range=11.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "loudnorm" in af
        assert "I=-16.0" in af
        assert "TP=-1.5" in af
        assert "LRA=11.0" in af

    def test_custom_lufs(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import normalize_audio
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            normalize_audio(inp, out, target_lufs=-23.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "I=-23.0" in af


class TestCompressAudio:
    def test_passes_acompressor_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import compress_audio
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            compress_audio(inp, out, threshold_db=-18.0, ratio=3.0, attack_ms=5.0, release_ms=50.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "acompressor" in af
        assert "threshold=-18.0dB" in af
        assert "ratio=3.0" in af
        assert "attack=5.0" in af
        assert "release=50.0" in af


class TestRemoveBackgroundNoise:
    def test_passes_afftdn_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import remove_background_noise
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            remove_background_noise(inp, out, noise_floor_db=-25.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "afftdn" in af
        assert "nf=-25.0" in af


class TestHighpassFilter:
    def test_passes_highpass_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import highpass_filter
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            highpass_filter(inp, out, cutoff_hz=80.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "highpass" in af
        assert "f=80.0" in af


class TestDeEss:
    def test_passes_equalizer_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import de_ess
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            de_ess(inp, out, frequency_hz=6000.0, bandwidth=2.0, gain_db=-5.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "equalizer" in af
        assert "f=6000.0" in af
        assert "w=2.0" in af
        assert "g=-5.0" in af


class TestRemoveSilence:
    def test_passes_silenceremove_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import remove_silence
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            remove_silence(inp, out, threshold_db=-40.0, min_duration=0.5)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "silenceremove" in af

    def test_trim_start_only(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import remove_silence
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            remove_silence(inp, out, trim_start=True, trim_end=False, trim_middle=False)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "start_periods" in af


class TestLimitPeaks:
    def test_passes_alimiter_filter(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import limit_peaks
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            limit_peaks(inp, out, limit_db=-1.0)
        args = mock_rf.call_args[0][0]
        af = args[args.index("-af") + 1]
        assert "alimiter" in af
        assert "limit=-1.0dB" in af


class TestConvertFormat:
    def test_passes_ar_ac_args(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import convert_format
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            convert_format(inp, out, sample_rate=44100, channels=1)
        args = mock_rf.call_args[0][0]
        assert "-ar" in args
        assert "44100" in args
        assert "-ac" in args
        assert "1" in args


class TestExportCompressed:
    def test_passes_bitrate_arg(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import export_compressed
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.mp3"
        with patch(_AUDIO_RUN_FFMPEG, return_value=_make_ffmpeg_result()) as mock_rf:
            export_compressed(inp, out, bitrate="192k")
        args = mock_rf.call_args[0][0]
        assert "-b:a" in args
        assert "192k" in args


# ---------------------------------------------------------------------------
# Voice enhance chain tests (mock individual tools)
# ---------------------------------------------------------------------------

_AUDIO_MODULE = "workshop_video_brain.edit_mcp.adapters.ffmpeg.audio"


def _patch_all_tools(success: bool = True):
    """Context manager that patches all audio tool functions."""
    return patch.multiple(
        _AUDIO_MODULE,
        highpass_filter=MagicMock(return_value=_make_ffmpeg_result(success=success)),
        remove_background_noise=MagicMock(return_value=_make_ffmpeg_result(success=success)),
        compress_audio=MagicMock(return_value=_make_ffmpeg_result(success=success)),
        de_ess=MagicMock(return_value=_make_ffmpeg_result(success=success)),
        normalize_audio=MagicMock(return_value=_make_ffmpeg_result(success=success)),
        limit_peaks=MagicMock(return_value=_make_ffmpeg_result(success=success)),
    )


class TestVoiceEnhanceChain:
    def test_youtube_voice_preset_runs_6_steps(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, preset="youtube_voice", dry_run=True)
        # 6 steps: highpass, denoise, compress, de_ess, normalize, limit
        assert len(result["steps"]) == 6
        assert result["preset_used"] == "youtube_voice"

    def test_podcast_preset_runs_6_steps(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, preset="podcast", dry_run=True)
        assert len(result["steps"]) == 6
        assert result["preset_used"] == "podcast"

    def test_raw_cleanup_preset_runs_6_steps(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, preset="raw_cleanup", dry_run=True)
        assert len(result["steps"]) == 6
        assert result["preset_used"] == "raw_cleanup"

    def test_include_de_ess_false_runs_5_steps(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, include_de_ess=False, dry_run=True)
        assert len(result["steps"]) == 5

    def test_dry_run_returns_commands_without_executing(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, dry_run=True)
        assert result["success"] is True
        assert "steps" in result

    def test_step_failure_stops_chain_returns_partial(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        # First step (highpass) fails
        with patch.multiple(
            _AUDIO_MODULE,
            highpass_filter=MagicMock(return_value=_make_ffmpeg_result(success=False)),
            remove_background_noise=MagicMock(return_value=_make_ffmpeg_result()),
            compress_audio=MagicMock(return_value=_make_ffmpeg_result()),
            de_ess=MagicMock(return_value=_make_ffmpeg_result()),
            normalize_audio=MagicMock(return_value=_make_ffmpeg_result()),
            limit_peaks=MagicMock(return_value=_make_ffmpeg_result()),
        ):
            result = voice_enhance_chain(inp, out)
        assert result["success"] is False
        assert len(result["steps"]) == 1
        assert result["final_output"] is None
        assert "error" in result

    def test_unknown_preset_falls_back_to_youtube_voice(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, preset="nonexistent_preset", dry_run=True)
        assert result["preset_used"] == "youtube_voice"

    def test_success_result_has_final_output(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        with _patch_all_tools():
            result = voice_enhance_chain(inp, out, dry_run=True)
        assert result["success"] is True
        assert result["final_output"] == str(out)

    def test_youtube_voice_uses_correct_params(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain, VOICE_PRESETS
        inp = tmp_path / "in.wav"
        inp.write_bytes(b"\x00")
        out = tmp_path / "out.wav"
        params = VOICE_PRESETS["youtube_voice"]
        hp_mock = MagicMock(return_value=_make_ffmpeg_result())
        with patch.multiple(
            _AUDIO_MODULE,
            highpass_filter=hp_mock,
            remove_background_noise=MagicMock(return_value=_make_ffmpeg_result()),
            compress_audio=MagicMock(return_value=_make_ffmpeg_result()),
            de_ess=MagicMock(return_value=_make_ffmpeg_result()),
            normalize_audio=MagicMock(return_value=_make_ffmpeg_result()),
            limit_peaks=MagicMock(return_value=_make_ffmpeg_result()),
        ):
            voice_enhance_chain(inp, out, preset="youtube_voice", dry_run=True)
        hp_call = hp_mock.call_args
        assert hp_call.kwargs.get("cutoff_hz") == float(params["highpass_hz"])


# ---------------------------------------------------------------------------
# Batch processing tests (mock voice_enhance_chain)
# ---------------------------------------------------------------------------

_BATCH_CHAIN = f"{_AUDIO_MODULE}.voice_enhance_chain"


class TestBatchProcess:
    def _success_chain(self, *args, **kwargs):
        out = kwargs.get("output_path", args[1] if len(args) > 1 else Path("/out.wav"))
        return {
            "success": True,
            "steps": [],
            "final_output": str(out),
            "preset_used": kwargs.get("preset", "youtube_voice"),
        }

    def _fail_chain(self, *args, **kwargs):
        return {
            "success": False,
            "steps": [],
            "final_output": None,
            "preset_used": kwargs.get("preset", "youtube_voice"),
            "error": "mock failure",
        }

    def test_processes_all_matching_files(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "a.wav").write_bytes(b"\x00")
        (raw / "b.mp3").write_bytes(b"\x00")
        (raw / "c.flac").write_bytes(b"\x00")
        out_dir = tmp_path / "processed"

        with patch(_BATCH_CHAIN, side_effect=self._success_chain):
            result = batch_process(raw, out_dir)

        assert result["processed"] == 3
        assert result["failed"] == 0
        assert len(result["results"]) == 3

    def test_skips_non_audio_files(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "a.wav").write_bytes(b"\x00")
        (raw / "b.txt").write_bytes(b"\x00")
        (raw / "c.xml").write_bytes(b"\x00")
        out_dir = tmp_path / "processed"

        with patch(_BATCH_CHAIN, side_effect=self._success_chain):
            result = batch_process(raw, out_dir)

        assert result["processed"] == 1
        assert "a.wav" in result["results"]
        assert "b.txt" not in result["results"]

    def test_reports_failure_count(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "a.wav").write_bytes(b"\x00")
        (raw / "b.wav").write_bytes(b"\x00")
        out_dir = tmp_path / "processed"

        with patch(_BATCH_CHAIN, side_effect=self._fail_chain):
            result = batch_process(raw, out_dir)

        assert result["failed"] == 2
        assert result["processed"] == 0

    def test_creates_output_dir(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "a.wav").write_bytes(b"\x00")
        out_dir = tmp_path / "processed" / "nested"

        with patch(_BATCH_CHAIN, side_effect=self._success_chain):
            batch_process(raw, out_dir)

        assert out_dir.exists()

    def test_custom_extensions(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "a.wav").write_bytes(b"\x00")
        (raw / "b.ogg").write_bytes(b"\x00")
        out_dir = tmp_path / "processed"

        with patch(_BATCH_CHAIN, side_effect=self._success_chain):
            result = batch_process(raw, out_dir, extensions={".ogg"})

        assert result["processed"] == 1
        assert "b.ogg" in result["results"]
        assert "a.wav" not in result["results"]


# ---------------------------------------------------------------------------
# Audio analyze tests (mock subprocess)
# ---------------------------------------------------------------------------

_TOOLS_SUBPROCESS = "subprocess.run"

LOUDNORM_STDERR = """
[Parsed_loudnorm_0 @ 0x...] {
	"input_i" : "-23.4",
	"input_tp" : "-8.2",
	"input_lra" : "14.2",
	"input_thresh" : "-34.1",
	"output_i" : "-16.0",
	"output_tp" : "-1.5",
	"output_lra" : "9.8",
	"normalization_type" : "dynamic",
	"target_offset" : "0.1"
}
"""


class TestAudioAnalyzeTool:
    def test_parses_lufs_from_ffmpeg_output(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_analyze
        ws = tmp_path
        raw = ws / "media" / "raw"
        raw.mkdir(parents=True)
        audio_file = raw / "voice.wav"
        audio_file.write_bytes(b"\x00")

        mock_proc = _make_proc_result(returncode=0, stderr=LOUDNORM_STDERR)
        with patch(_TOOLS_SUBPROCESS, return_value=mock_proc):
            result = audio_analyze(str(ws), str(audio_file))

        assert result["status"] == "success"
        d = result["data"]
        assert d["integrated_lufs"] == pytest.approx(-23.4)
        assert d["true_peak_db"] == pytest.approx(-8.2)
        assert d["loudness_range"] == pytest.approx(14.2)

    def test_returns_error_on_missing_json(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_analyze
        ws = tmp_path
        raw = ws / "media" / "raw"
        raw.mkdir(parents=True)
        audio_file = raw / "voice.wav"
        audio_file.write_bytes(b"\x00")

        mock_proc = _make_proc_result(returncode=1, stderr="garbled output no json here")
        with patch(_TOOLS_SUBPROCESS, return_value=mock_proc):
            result = audio_analyze(str(ws), str(audio_file))

        assert result["status"] == "error"

    def test_returns_error_when_no_file_found(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_analyze
        ws = tmp_path
        # No media/raw directory
        result = audio_analyze(str(ws), "")
        assert result["status"] == "error"

    def test_latest_file_found_without_explicit_path(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_analyze
        ws = tmp_path
        raw = ws / "media" / "raw"
        raw.mkdir(parents=True)
        audio_file = raw / "voice.wav"
        audio_file.write_bytes(b"\x00")

        mock_proc = _make_proc_result(returncode=0, stderr=LOUDNORM_STDERR)
        with patch(_TOOLS_SUBPROCESS, return_value=mock_proc):
            result = audio_analyze(str(ws))  # no file_path

        assert result["status"] == "success"
