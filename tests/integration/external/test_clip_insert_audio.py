"""Real-melt proof that clip_insert preserves source audio."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import call_tool, make_test_clip, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from tests.integration.external._oracle import audio_stats, render_video

pytestmark = [pytest.mark.external, requires_ffmpeg_ffprobe, requires_melt_ffmpeg]


def test_clip_insert_audio_is_audible(tmp_path: Path, melt_bin: str, ffmpeg_bin: str):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle, timeline_project, workspace_media

    media_root = tmp_path / "media"
    media_root.mkdir()
    created = call_tool(workspace_media.workspace_create, title="Audio render proof", media_root=str(media_root))
    assert created["status"] == "success", created
    workspace = Path(created["data"]["workspace_root"])
    initialized = call_tool(timeline_project.project_create_working_copy, str(workspace))
    assert initialized["status"] == "success", initialized
    source = make_test_clip(tmp_path / "tone.mp4", duration=3, with_audio=True, freq=440)
    inserted = call_tool(clips_nle.clip_insert, str(workspace), str(source), out_seconds=2.96)
    assert inserted["status"] == "success" and inserted["data"]["audio_placed"], inserted
    project = Path(inserted["data"]["kdenlive_path"])
    output = render_video(project, tmp_path / "audio_insert.mp4", frames=75, melt_bin=melt_bin)
    rms = audio_stats(output, ffmpeg_bin).get("RMS level dB", float("-inf"))
    assert rms > -60, f"clip_insert render is silent: RMS={rms:.1f} dB"
