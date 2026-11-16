"""A selects timeline renders exactly the selected seconds (ROADMAP next #2).

Before the fix every clip's out-point was ``seconds_to_frames(end)``, so each
select rendered one frame too long; two 1 s selects at 25 fps came out 52
frames instead of 50.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import make_test_clip, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from workshop_video_brain.core.models.kdenlive import ProjectProfile
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
    SelectsEntry,
    build_selects_timeline,
)
from ._oracle import melt_accepts, melt_render_full, video_frame_count

pytestmark = [pytest.mark.external, requires_ffmpeg_ffprobe, requires_melt_ffmpeg]


def _select(clip: Path, start: float, end: float, reason: str) -> SelectsEntry:
    marker = Marker(
        category="step_explanation", confidence_score=0.9, start_seconds=start,
        end_seconds=end, clip_ref=str(clip), reason=reason,
    )
    return SelectsEntry(
        marker=marker, clip_ref=str(clip), start_seconds=start, end_seconds=end,
        reason=reason, usefulness_score=0.81,
    )


def test_selects_render_exact_frame_count(tmp_path, melt_bin, ffprobe_bin):
    (tmp_path / "media").mkdir()
    clip = make_test_clip(tmp_path / "media" / "bars.mp4", duration=4, fps=25, size=(320, 240))
    selects = [_select(clip, 2.0, 3.0, "second"), _select(clip, 0.0, 1.0, "first")]
    profile = ProjectProfile(width=320, height=240, fps=25.0)
    project = build_selects_timeline(selects, [], tmp_path / "ws", profile=profile)
    assert melt_accepts(project, melt_bin=melt_bin).ok

    out = melt_render_full(project, tmp_path / "selects.mp4", melt_bin)
    assert video_frame_count(out, ffprobe_bin) == 50
