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
from ._oracle import frames_differ, render_frame

pytestmark = pytest.mark.external

FPS = 25.0
EACH = 25  # frames per clip; cut at frame 25
CUT = EACH


def _render(proj, name, frame, render_dir, melt_bin):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    return render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}_f{frame}.png")


@pytest.mark.xfail(
    strict=True,
    reason="§1.1: transition pseudo-XML (no mlt_service, not in tractor) is "
    "ignored by MLT -- the cut is hard, no blend. Flips to pass with a real "
    "tractor mix transition.",
)
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
