"""Silence cut against real media (the analogue of test_audio_ffmpeg_smoke.py).

Duration, loudness and leftover silence are measured on the output, because
"ffmpeg returned 0" says nothing about whether the silence went away.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests._testkit import _run_ffmpeg, call_tool, requires_auto_editor, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.server.bundles.media_remove_silence import (
    media_remove_silence,
    media_silence_keep_ranges,
)

pytestmark = requires_ffmpeg_ffprobe

FIXTURE = Path(__file__).parents[1] / "fixtures/media_generated/test_audio_with_silence.mp4"
ENGINES = ["ffmpeg", pytest.param("auto-editor", marks=requires_auto_editor)]


def _ffmpeg_stderr(path: Path, audio_filter: str) -> str:
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", audio_filter, "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    ).stderr


def _mean_volume(path: Path) -> float:
    return float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", _ffmpeg_stderr(path, "volumedetect")).group(1))


def _silences(path: Path) -> list[str]:
    return re.findall(r"silence_start", _ffmpeg_stderr(path, "silencedetect=n=-40dB:d=0.5"))


@pytest.mark.parametrize("engine", ENGINES)
def test_video_with_silence(tmp_path, engine):
    output = tmp_path / "tight.mp4"
    result = call_tool(media_remove_silence, str(FIXTURE), str(output), engine=engine)
    assert result["status"] == "success", result
    assert result["data"]["engine"] == engine

    asset = probe_media(output)
    assert 3.0 <= asset.duration <= 3.8
    assert asset.video_codec and asset.audio_codec
    assert _mean_volume(output) > -40
    assert _mean_volume(output) > _mean_volume(FIXTURE)
    assert _silences(output) == []
    assert _silences(FIXTURE) != [], "the control must see the silence this removes"


@requires_auto_editor
def test_engines_agree_within_tolerance():
    ranges = {
        engine: call_tool(media_silence_keep_ranges, str(FIXTURE), engine=engine)["data"]["keep_ranges"]
        for engine in ("ffmpeg", "auto-editor")
    }
    assert len(ranges["ffmpeg"]) == len(ranges["auto-editor"]) == 2
    for ours, theirs in zip(ranges["ffmpeg"], ranges["auto-editor"]):
        assert ours[0] == pytest.approx(theirs[0], abs=0.15)
        assert ours[1] == pytest.approx(theirs[1], abs=0.15)


@pytest.mark.parametrize("engine", ENGINES)
def test_audio_only_input_stays_audio_only(tmp_path, engine):
    source = tmp_path / "gap.wav"
    _run_ffmpeg([
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=48000",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=2",
        "-f", "lavfi", "-i", "sine=frequency=660:duration=2:sample_rate=48000",
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]", "-map", "[a]", str(source),
    ])
    output = tmp_path / "tight.wav"
    result = call_tool(media_remove_silence, str(source), str(output), engine=engine)
    assert result["status"] == "success", result
    asset = probe_media(output)
    assert not asset.video_codec
    assert 4.0 <= asset.duration <= 4.8
    assert _silences(output) == []


def test_all_silent_file_is_refused_and_writes_nothing(tmp_path):
    source = tmp_path / "quiet.wav"
    _run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=2", str(source)])
    output = tmp_path / "tight.wav"
    result = call_tool(media_remove_silence, str(source), str(output), engine="ffmpeg")
    assert result["error_type"] == "invalid_input"
    assert "silent" in result["message"]
    assert not output.exists()


def test_same_output_as_source_is_refused(tmp_path):
    source = tmp_path / "copy.mp4"
    source.write_bytes(FIXTURE.read_bytes())
    before = source.read_bytes()
    result = call_tool(media_remove_silence, str(source), str(source), engine="ffmpeg")
    assert result["error_type"] == "invalid_input"
    assert source.read_bytes() == before


def test_unreadable_source_is_reported(tmp_path):
    source = tmp_path / "garbage.mp4"
    source.write_bytes(bytes(range(256)) * 4)
    result = call_tool(media_silence_keep_ranges, str(source), engine="ffmpeg")
    assert result["status"] == "error"
    assert result["error_type"] == "media_unreadable"
