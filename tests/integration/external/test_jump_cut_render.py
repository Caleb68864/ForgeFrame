"""A jump-cut timeline renders at the source's size and rate, without its silence."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from workshop_video_brain.edit_mcp.server.bundles.jump_cut import timeline_build_jump_cut
from workshop_video_brain.workspace.manager import WorkspaceManager
from ._oracle import audio_stats, melt_accepts, probe, render_video

pytestmark = [pytest.mark.external, requires_ffmpeg_ffprobe, requires_melt_ffmpeg]

MEDIA = Path(__file__).parents[2] / "fixtures/media_generated"


def _workspace(tmp_path: Path, fixture: str) -> tuple[Path, Path]:
    root = tmp_path / "ws"
    WorkspaceManager.create("Jump cut", tmp_path, workspace_root=root)
    source = root / fixture
    shutil.copyfile(MEDIA / fixture, source)
    return root, source


def test_silence_cut_renders_source_sized_and_gapless(tmp_path, melt_bin, ffmpeg_bin, ffprobe_bin):
    root, source = _workspace(tmp_path, "test_audio_with_silence.mp4")
    result = call_tool(timeline_build_jump_cut, str(root), str(source), engine="ffmpeg", add_cut_guides=True)
    assert result["status"] == "success", result
    data = result["data"]
    assert data["profile"] == {"width": 320, "height": 180, "fps": 30.0}
    assert data["audio_placed"] is True
    assert data["keep_ranges"] == [[0.0, 1.699917], [3.300062, 5.0]]
    project = Path(data["kdenlive_path"])
    assert melt_accepts(project, melt_bin=melt_bin).ok

    output = render_video(project, tmp_path / "jump.mp4", frames=data["timeline_frames"], melt_bin=melt_bin)
    info = probe(output)
    assert (info.width, info.height) == (320, 180)
    assert info.fps == pytest.approx(30.0, abs=0.01)
    assert info.duration == pytest.approx(data["kept_seconds"], abs=2 / 30)
    assert audio_stats(output, ffmpeg_bin)["RMS level dB"] > -40

    detected = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-i", str(output), "-af", "silencedetect=n=-40dB:d=0.5", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    ).stderr
    assert re.findall("silence_start", detected) == []


def test_explicit_ranges_keep_an_ntsc_rate(tmp_path, melt_bin):
    root, source = _workspace(tmp_path, "test_clip_1080p2997_5s.mp4")
    result = call_tool(timeline_build_jump_cut, str(root), str(source), keep_ranges_json="[[0.5, 2.0], [3.0, 4.5]]")
    assert result["status"] == "success", result
    data = result["data"]
    assert data["engine"] == "explicit"
    project = Path(data["kdenlive_path"])
    assert "atsc_1080p_2997" in project.read_text(encoding="utf-8")
    assert melt_accepts(project, melt_bin=melt_bin).ok

    output = render_video(project, tmp_path / "ntsc.mp4", frames=data["timeline_frames"], melt_bin=melt_bin)
    assert probe(output).fps == pytest.approx(30000 / 1001, abs=0.01)
