"""transition-renders: a transition should produce a blended frame at the cut.

Two adjacent clips (red then blue) plus a crossfade should yield, at the cut, a
frame that is neither pure red nor pure blue (an actual blend). The current
``AddTransition`` emits pseudo-XML (no mlt_service, not in the tractor) that MLT
ignores, so the cut is hard and the mid frame is one of the two solids.

xfail(strict): flips to passing when transitions emit a real tractor mix.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import AddTransition
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import frames_differ, mean_color, render_frame

pytestmark = pytest.mark.external

FPS = 25.0
EACH = 25  # frames per clip; cut at frame 25
CUT = EACH


def _render(proj, name, frame, render_dir, melt_bin):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    return render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}_f{frame}.png")


def test_transition_blends_at_cut(melt_bin, render_dir: Path):
    # Reference solids.
    red_ref = _render(
        builders.solid_color_project(color=builders.RED, frames=EACH, fps=FPS),
        "tr_red", 5, render_dir, melt_bin,
    )
    blue_ref = _render(
        builders.solid_color_project(color=builders.BLUE, frames=EACH, fps=FPS),
        "tr_blue", 5, render_dir, melt_bin,
    )

    proj = builders.sequence_project(colors=[builders.RED, builders.BLUE], frames_each=EACH, fps=FPS)
    proj = patcher.patch_project(
        proj,
        [AddTransition(type="luma", track_ref=builders.VIDEO_TRACK,
                       left_clip_ref="0", right_clip_ref="1", duration_frames=12)],
    )
    mid = _render(proj, "tr_mix", CUT, render_dir, melt_bin)

    # A real blend differs from BOTH pure sources.
    assert frames_differ(mid, red_ref) and frames_differ(mid, blue_ref), (
        "mid-cut frame matches a pure source -- no blend happened"
    )


def test_dissolve_without_handles_blends_real_footage(melt_bin, render_dir: Path):
    """Clips with no spare frames: the overlap comes from pulling the right
    clip earlier, never from stretching the left clip past its media (which
    melt renders as black and Kdenlive trims). Every overlap frame mixes red
    and blue -- including the last one, where the old layout went black."""
    proj = builders.sequence_project(colors=[builders.RED, builders.BLUE], frames_each=EACH, fps=FPS)
    for p in proj.producers:
        p.properties["length"] = str(EACH)
    proj = patcher.patch_project(
        proj,
        [AddTransition(type="dissolve", track_ref=builders.VIDEO_TRACK,
                       left_clip_ref="0", right_clip_ref="1", duration_frames=12)],
    )
    # Overlap is frames EACH-12 .. EACH-1.
    for frame in (EACH - 9, EACH - 6, EACH - 3):
        r, g, b = mean_color(_render(proj, f"tr_nohandle_{frame}", frame, render_dir, melt_bin))
        assert r > 20 and b > 20, f"frame {frame} is not a red/blue mix: {(r, g, b)}"
    # Red fades out as the dissolve progresses.
    early = mean_color(_render(proj, "tr_nohandle_early", EACH - 10, render_dir, melt_bin))
    late = mean_color(_render(proj, "tr_nohandle_late", EACH - 2, render_dir, melt_bin))
    assert early[0] > late[0] and early[2] < late[2]
