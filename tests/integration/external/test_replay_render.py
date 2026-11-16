"""A replay reel renders exactly its padded segments (ROADMAP next #2 follow-up).

``generate_replay`` used ``seconds_to_frames(seg_end)`` as the inclusive MLT
out-point, the same off-by-one PR #10 fixed in ``build_selects_timeline``: each
segment rendered one frame too long. Two markers padded to 0-5 s and 10-15 s at
25 fps must render 250 frames, not 252.

The 24-frame crossfade between segments was a bare ``<transition>`` with no
``mlt_service``: melt logged ``failed to load transition "(null)"``, skipped
it, and the reel had hard cuts. It is now a ``luma`` dissolve over an overlap
(the incoming segment is pulled 24 frames earlier, so 250 -> 226 frames), and
the middle of the overlap is a blend of both sources.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from tests._testkit import make_test_clip, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.edit_mcp.pipelines.replay_generator import generate_replay
from ._oracle import (
    mean_color,
    melt_accepts,
    melt_render_full,
    render_frame,
    video_frame_count,
)

pytestmark = [pytest.mark.external, requires_ffmpeg_ffprobe, requires_melt_ffmpeg]


def test_replay_render_exact_frame_count(tmp_path, melt_bin, ffprobe_bin):
    ws = tmp_path / "ws"
    (ws / "markers").mkdir(parents=True)
    clip = make_test_clip(tmp_path / "bars.mp4", duration=16, fps=25, size=(320, 240))
    markers = [
        Marker(category="step_explanation", confidence_score=0.9, start_seconds=2.0,
               end_seconds=3.0, clip_ref=str(clip), reason="first"),
        Marker(category="step_explanation", confidence_score=0.8, start_seconds=12.0,
               end_seconds=13.0, clip_ref=str(clip), reason="second"),
    ]
    (ws / "markers" / "bars_markers.json").write_text(
        json.dumps([m.model_dump(mode="json") for m in markers]), encoding="utf-8"
    )
    project = generate_replay(ws, target_duration=9999.0)

    root = ET.parse(project).getroot()
    # Padded 0-5 s and 10-15 s, not merged; the second sits on the
    # crossfade track.
    spans = [(e.get("in"), e.get("out"))
             for p in root.iter("playlist")
             if p.get("id") in ("playlist_video", "playlist_video_xfade0")
             for e in p.findall("entry")]
    assert spans == [("0", "124"), ("250", "374")], spans

    assert melt_accepts(project, melt_bin).ok

    out = melt_render_full(project, tmp_path / "replay.mp4", melt_bin)
    assert video_frame_count(out, ffprobe_bin) == 226  # 250 - 24-frame overlap


def test_replay_crossfade_blends(tmp_path, melt_bin):
    ws = tmp_path / "ws"
    (ws / "markers").mkdir(parents=True)
    red = make_test_clip(tmp_path / "red.mp4", kind="color", color="red", duration=16)
    blue = make_test_clip(tmp_path / "blue.mp4", kind="color", color="blue", duration=16)
    markers = [
        Marker(category="step_explanation", confidence_score=0.9, start_seconds=2.0,
               end_seconds=3.0, clip_ref=str(red), reason="red"),
        Marker(category="step_explanation", confidence_score=0.8, start_seconds=12.0,
               end_seconds=13.0, clip_ref=str(blue), reason="blue"),
    ]
    (ws / "markers" / "m_markers.json").write_text(
        json.dumps([m.model_dump(mode="json") for m in markers]), encoding="utf-8"
    )
    project = generate_replay(ws, target_duration=9999.0)

    # The "blue" guide moves with its pulled-in segment.
    guides = {g.get("comment"): g.get("position") for g in ET.parse(project).getroot().iter("guide")}
    assert sorted(guides.items()) == [("Highlight: blue", "101"), ("Highlight: red", "0")], guides

    res = melt_accepts(project, melt_bin, frames=226)
    assert "failed to load transition" not in res.stderr, res.stderr[-1500:]
    assert res.ok, res.stderr[-1500:]

    # Red is timeline 0-124; blue is pulled in at 101, overlap 101-124.
    before = mean_color(render_frame(project, 90, tmp_path, melt_bin, name="a.png"))
    mid = mean_color(render_frame(project, 112, tmp_path, melt_bin, name="m.png"))
    after = mean_color(render_frame(project, 140, tmp_path, melt_bin, name="b.png"))
    # (Means include the pillarbox: 4:3 clips in a 16:9 profile.)
    r, b = before[0], after[2]
    assert r > 100 and before[2] < 30, before
    assert b > 100 and after[0] < 30, after
    # A hard cut would leave frame 112 pure red; mid-overlap carries both.
    assert 0.25 * r < mid[0] < 0.75 * r, (before, mid, after)
    assert 0.25 * b < mid[2] < 0.75 * b, (before, mid, after)
