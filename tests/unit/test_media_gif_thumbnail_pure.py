"""Command builders for media_gif / media_thumbnail (prompt 32; no ffmpeg)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.clip_preview import (
    mp4_preview_command,
    palettegen_command,
    paletteuse_command,
    webp_preview_command,
)
from workshop_video_brain.edit_mcp.pipelines.media_thumbnail import thumbnail_args

I, P, O = Path("/in.mp4"), Path("/p.png"), Path("/o.gif")


def test_start_zero_keeps_old_argv():
    assert palettegen_command(I, P, 2.0, 12, 320) == [
        "ffmpeg", "-y", "-t", "2.0000", "-i", "/in.mp4", "-vf", "fps=12,scale=320:-2:flags=lanczos,palettegen", "/p.png"]
    assert paletteuse_command(I, P, O, 2.0, 12, 320) == [
        "ffmpeg", "-y", "-t", "2.0000", "-i", "/in.mp4", "-i", "/p.png",
        "-lavfi", "fps=12,scale=320:-2:flags=lanczos[x];[x][1:v]paletteuse", "-loop", "0", "/o.gif"]
    assert mp4_preview_command(I, O, 2.0, 12, 320)[:6] == ["ffmpeg", "-y", "-t", "2.0000", "-i", "/in.mp4"]


@pytest.mark.parametrize("builder", [
    lambda s: palettegen_command(I, P, 1.0, 10, 160, start=s),
    lambda s: paletteuse_command(I, P, O, 1.0, 10, 160, start=s),
    lambda s: mp4_preview_command(I, O, 1.0, 10, 160, start=s),
    lambda s: webp_preview_command(I, O, 1.0, 10, 160, start=s),
])
def test_start_seeks_before_the_first_input(builder):
    cmd = builder(2.5)
    assert cmd.index("-ss") < cmd.index("-i") and cmd[cmd.index("-ss") + 1] == "2.5000"


def test_webp_and_thumbnail_args():
    cmd = webp_preview_command(I, Path("/o.webp"), 1.0, 10, 160)
    assert "libwebp_anim" in cmd and cmd[cmd.index("-loop") + 1] == "0"
    auto = thumbnail_args(None, 640, 25.0, 4.0, ".jpg")
    assert auto[1] == "thumbnail=n=100,scale=640:-2" and "-q:v" in auto
    assert thumbnail_args(1.0, 0, 25.0, 4.0, ".png") == ["-frames:v", "1"]
    with pytest.raises(ValueError):
        thumbnail_args(1.0, 0, 25.0, 4.0, ".bmp")
