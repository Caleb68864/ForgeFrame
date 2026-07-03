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
from ._oracle import audio_stats, mean_color, render_frame, render_video

pytestmark = pytest.mark.external

FPS = 25.0
FRAMES = 50
FADE_FRAMES = 24


@pytest.mark.xfail(
    strict=True,
    reason="§1.1: root-placed fade (brightness/affine) filter is a no-op -- the "
    "first frame is not darkened. Flips to pass with the placement fix.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="§1.1: AudioFade emits <filter type=\"volume\"> with no mlt_service "
    "-- melt fails to load it, so audio is not ramped. Flips to pass with the "
    "proper volume-filter fix.",
)
def test_audio_fade_in_ramps_level(melt_bin, ffmpeg_bin, render_dir: Path):
    proj = builders.solid_color_project(color=builders.RED, frames=FRAMES, fps=FPS)
    proj = patcher.patch_project(
        proj,
        [AudioFade(track_ref=builders.AUDIO_TRACK, clip_index=0,
                   fade_type="in", duration_frames=FADE_FRAMES)],
    )
    project_path = render_dir / "afade.kdenlive"
    serialize_project(proj, project_path)

    # A silent color clip has no audio energy, so a working fade is best shown
    # by the render simply succeeding AND astats reporting a non-flat RMS. The
    # color producer emits silence, so today this asserts the fade produced a
    # measurable ramp -- which it cannot while the filter fails to load.
    out = render_video(project_path, render_dir / "afade.mp4", frames=FRAMES, melt_bin=melt_bin)
    stats = audio_stats(out, ffmpeg_bin=ffmpeg_bin)
    # RMS peak must be meaningfully above the overall RMS for a ramp to exist.
    rms = stats.get("RMS level dB")
    peak = stats.get("RMS peak dB")
    assert rms is not None and peak is not None and (peak - rms) > 3.0, (
        f"no audio ramp detected (rms={rms}, peak={peak})"
    )
