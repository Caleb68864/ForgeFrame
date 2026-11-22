"""Waveform argument checks and measure_loudness's timeout (prompt 35; no ffmpeg)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg import probe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import ANALYSIS_TIMEOUT_SECONDS
from workshop_video_brain.edit_mcp.pipelines.audio_files import check_color, waveform_args


@pytest.mark.parametrize("ok", ["0x3399ff", "0x3399ffcc", "red"])
def test_colors_accepted(ok):
    assert check_color(ok) == ok


@pytest.mark.parametrize("bad", ["red:x=1", "0x33", "'; rm", "Red"])
def test_colors_rejected(bad):
    with pytest.raises(ValueError):
        check_color(bad)


def test_waveform_args():
    args = waveform_args(1600, 300, "0x3399ff", False, None)
    assert "showwavespic=s=1600x300:split_channels=0:colors=0x3399ff" in args and args[-2:] == ["-frames:v", "1"]
    with pytest.raises(ValueError):
        waveform_args(10, 300, "red", False, None)


def test_measure_loudness_uses_the_analysis_timeout(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    probe.measure_loudness(Path(f))
    assert seen["timeout"] == ANALYSIS_TIMEOUT_SECONDS
