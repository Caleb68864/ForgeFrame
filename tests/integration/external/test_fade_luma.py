"""fade-luma: a fade-in should darken the first frame (and audio should ramp).

Both fade paths attach their filter at the MLT root today (§1.1), so neither is
applied by melt: the first video frame stays bright and the audio does not
ramp. Both tests are xfail(strict) and flip when the placement fix lands.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import AudioFade
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import mean_color, render_frame, render_video

pytestmark = pytest.mark.external

FPS = 25.0
FRAMES = 50
FADE_FRAMES = 24


def test_video_fade_in_darkens_first_frame(melt_bin, render_dir: Path):
    # White clip: without a fade the first frame is bright; a working fade-in
    # from black makes frame 0 near-black.
    proj = builders.solid_color_project(color=builders.WHITE, frames=FRAMES, fps=FPS)
    xml = builders.build_filter_xml(
        "brightness", track=0, clip=0, props=[("level", f"0=0;{FADE_FRAMES}=1")]
    )
    patcher.insert_effect_xml(proj, (0, 0), xml, position=0)

    project_path = render_dir / "fade.kdenlive"
    serialize_project(proj, project_path)
    frame0 = render_frame(project_path, 0, render_dir, melt_bin=melt_bin, name="fade0.png")

    r, g, b = mean_color(frame0)
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    assert luma < 40.0, f"fade-in first frame not dark (luma={luma:.1f})"


def _window_rms_db(ffmpeg_bin: str, media, start: float, dur: float | None) -> float:
    """Overall RMS level (dB) of a time window of *media* via ffmpeg astats."""
    import subprocess

    cmd = [ffmpeg_bin, "-hide_banner", "-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(media), "-af", "astats=metadata=1:reset=0", "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    val = None
    for line in proc.stderr.splitlines():
        if "RMS level dB:" in line:
            try:
                val = float(line.split("RMS level dB:", 1)[1].strip())
            except ValueError:
                pass
    return val if val is not None else float("-inf")


def test_audio_fade_in_ramps_level(melt_bin, ffmpeg_bin, render_dir: Path):
    """A fade-in must leave the clip's start much quieter than its end.

    builders' ``color`` producer is silent, so the audio track is re-pointed at
    an MLT ``tone`` producer (an audible source) to make the ramp observable.
    The AudioFade code path (patcher volume filter, entry-nested by the
    serializer) is exercised exactly as in production.
    """
    from workshop_video_brain.core.models.kdenlive import Producer

    proj = builders.solid_color_project(color=builders.RED, frames=FRAMES, fps=FPS)
    # Give the audio track an audible source (a tone) so the fade is measurable.
    proj.producers.append(
        Producer(
            id="tone_0",
            resource="",
            properties={"mlt_service": "tone", "length": str(FRAMES + 10)},
        )
    )
    audio_pl = next(p for p in proj.playlists if p.id == builders.AUDIO_TRACK)
    audio_pl.entries[0].producer_id = "tone_0"

    proj = patcher.patch_project(
        proj,
        [AudioFade(track_ref=builders.AUDIO_TRACK, clip_index=0,
                   fade_type="in", duration_frames=FADE_FRAMES)],
    )
    project_path = render_dir / "afade.kdenlive"
    serialize_project(proj, project_path)

    out = render_video(project_path, render_dir / "afade.mp4", frames=FRAMES, melt_bin=melt_bin)

    fade_secs = FADE_FRAMES / FPS
    early = _window_rms_db(ffmpeg_bin, out, 0.0, fade_secs * 0.4)
    late = _window_rms_db(ffmpeg_bin, out, fade_secs + 0.1, None)
    # A working fade-in leaves the opening near-silent and the tail at full
    # level -- a large, unmistakable ramp.
    assert late - early > 6.0, (
        f"no audio ramp detected (early={early:.1f} dB, late={late:.1f} dB)"
    )
