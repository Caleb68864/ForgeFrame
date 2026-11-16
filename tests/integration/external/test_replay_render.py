"""A replay reel renders exactly its padded segments (ROADMAP next #2 follow-up).

``generate_replay`` used ``seconds_to_frames(seg_end)`` as the inclusive MLT
out-point, the same off-by-one PR #10 fixed in ``build_selects_timeline``: each
segment rendered one frame too long. Two markers padded to 0-5 s and 10-15 s at
25 fps must render 250 frames, not 252.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from tests._testkit import make_test_clip, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.edit_mcp.pipelines.replay_generator import generate_replay
from ._oracle import melt_render_full, video_frame_count

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
    video_pl = next(p for p in root.iter("playlist") if p.get("id") == "playlist_video")
    spans = [(e.get("in"), e.get("out")) for e in video_pl.findall("entry")]
    assert len(spans) == 2, spans  # padded 0-5 s and 10-15 s, not merged

    # Not melt_accepts(): the replay's crossfade <transition> has no
    # mlt_service, so melt logs 'failed to load transition "(null)"' and
    # ignores it (a separate, known defect). The render itself completes.
    out = melt_render_full(project, tmp_path / "replay.mp4", melt_bin)
    assert video_frame_count(out, ffprobe_bin) == 250
