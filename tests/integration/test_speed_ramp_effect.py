"""Integration tests for the speed-ramp patcher path and the ``speed_ramp`` tool.

Exercises the real patch -> serialize -> re-parse round trip (no melt required)
and the full MCP bundle tool end-to-end against a minimal Kdenlive project.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import SpeedRamp
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr
from workshop_video_brain.edit_mcp.server.bundles import speed_ramp as _bundle
from workshop_video_brain.workspace.manager import WorkspaceManager

# @mcp.tool() wraps the callable; raw fn lives on .fn under pytest config.
speed_ramp = getattr(_bundle.speed_ramp, "fn", _bundle.speed_ramp)

FPS = 25.0
CLIP_FRAMES = 100


def _two_phase_segments():
    kfs = [
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ]
    segs = sr.plan_segments(kfs, clip_frames=CLIP_FRAMES, fps=FPS, easing="linear")
    return [(s.src_in, s.src_out, s.speed) for s in segs], segs


def _one_track_project(with_audio: bool = False) -> KdenliveProject:
    producers = [
        Producer(
            id="clipsrc",
            resource="/tmp/does-not-matter.mp4",
            properties={"resource": "/tmp/does-not-matter.mp4", "length": str(CLIP_FRAMES + 10)},
        )
    ]
    tracks = [Track(id="playlist_video", track_type="video")]
    playlists = [
        Playlist(
            id="playlist_video",
            entries=[PlaylistEntry(producer_id="clipsrc", in_point=0, out_point=CLIP_FRAMES - 1)],
        )
    ]
    if with_audio:
        tracks.append(Track(id="playlist_audio", track_type="audio"))
        playlists.append(
            Playlist(
                id="playlist_audio",
                entries=[PlaylistEntry(producer_id="clipsrc", in_point=0, out_point=CLIP_FRAMES - 1)],
            )
        )
    return KdenliveProject(
        title="ramp",
        profile=ProjectProfile(width=320, height=240, fps=FPS),
        producers=producers,
        tracks=tracks,
        playlists=playlists,
        tractor={"id": "tractor0", "in": "0", "out": str(CLIP_FRAMES - 1)},
    )


# ---------------------------------------------------------------------------
# patcher round-trip
# ---------------------------------------------------------------------------

def test_patcher_creates_timewarp_producers_and_segments():
    seg_tuples, segs = _two_phase_segments()
    project = _one_track_project()
    patched = patcher.patch_project(
        project, [SpeedRamp(track_ref="playlist_video", clip_index=0, segments=seg_tuples)]
    )
    tw = [p for p in patched.producers if p.properties.get("mlt_service") == "timewarp"]
    assert {p.id for p in tw} == {"clipsrc_tw2", "clipsrc_tw0.5"}
    # each timewarp resource carries the speed prefix
    assert any(p.resource.startswith("2:") for p in tw)
    assert any(p.resource.startswith("0.5:") for p in tw)

    entries = [e for e in patched.playlists[0].entries if e.producer_id]
    assert len(entries) == len(seg_tuples)
    total = sum(e.out_point - e.in_point + 1 for e in entries)
    assert total == sr.total_output_frames(0, segs) == 125


def test_patcher_survives_serialize_reparse(tmp_path):
    seg_tuples, segs = _two_phase_segments()
    project = _one_track_project()
    patched = patcher.patch_project(
        project, [SpeedRamp(track_ref="playlist_video", clip_index=0, segments=seg_tuples)]
    )
    out = tmp_path / "ramp_roundtrip.kdenlive"
    serialize_project(patched, out)
    reparsed = parse_project(out)
    tw_ids = {p.id for p in reparsed.producers if p.properties.get("mlt_service") == "timewarp"}
    assert "clipsrc_tw2" in tw_ids and "clipsrc_tw0.5" in tw_ids
    video = next(pl for pl in reparsed.playlists if pl.id == "playlist_video")
    entries = [e for e in video.entries if e.producer_id]
    assert sum(e.out_point - e.in_point + 1 for e in entries) == 125


def test_patcher_ramps_linked_audio_in_lockstep():
    seg_tuples, _ = _two_phase_segments()
    project = _one_track_project(with_audio=True)
    patched = patcher.patch_project(
        project, [SpeedRamp(track_ref="playlist_video", clip_index=0, segments=seg_tuples)]
    )
    audio = next(pl for pl in patched.playlists if pl.id == "playlist_audio")
    audio_entries = [e for e in audio.entries if e.producer_id]
    # audio track received the same number of ramp segments as the video track
    assert len(audio_entries) == len(seg_tuples)
    assert all(e.producer_id.startswith("clipsrc_tw") for e in audio_entries)


def test_pitch_compensation_sets_warp_pitch():
    seg_tuples, _ = _two_phase_segments()
    project = _one_track_project()
    patched = patcher.patch_project(
        project,
        [SpeedRamp(track_ref="playlist_video", clip_index=0, segments=seg_tuples,
                   pitch_compensation=True)],
    )
    tw = [p for p in patched.producers if p.properties.get("mlt_service") == "timewarp"]
    assert tw and all(p.properties.get("warp_pitch") == "1" for p in tw)


# ---------------------------------------------------------------------------
# full MCP bundle tool
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_ws(tmp_path):
    ws = WorkspaceManager.create(
        title="Ramp Test",
        media_root=str(tmp_path / "raw_media"),
        workspace_root=tmp_path / "workspace",
    )
    ws_root = Path(ws.workspace_root)
    project = _one_track_project()
    proj_rel = "projects/working_copies/ramp.kdenlive"
    proj_path = ws_root / proj_rel
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    serialize_project(project, proj_path)
    reparsed = parse_project(proj_path)
    track = next(
        i for i, pl in enumerate(reparsed.playlists)
        if any(e.producer_id for e in pl.entries)
    )
    return ws_root, proj_rel, track


def test_tool_applies_ramp_and_reports_frames(project_ws):
    import json

    ws_root, proj_rel, track = project_ws
    kfs = json.dumps([
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ])
    res = speed_ramp(str(ws_root), proj_rel, track=track, clip_index=0, keyframes=kfs, easing="linear")
    assert res["status"] == "success", res
    data = res["data"]
    assert data["keyframe_format"] == "speed"
    assert data["segment_count"] >= 2
    assert data["expected_output_frames"] == 125
    assert data["snapshot_id"]

    # The written project now contains timewarp producers.
    reparsed = parse_project(ws_root / proj_rel)
    tw = [p for p in reparsed.producers if p.properties.get("mlt_service") == "timewarp"]
    assert tw


def test_tool_accepts_timemap_format(project_ws):
    import json

    ws_root, proj_rel, track = project_ws
    kfs = json.dumps([
        {"output_seconds": 0, "source_seconds": 0},
        {"output_seconds": 4, "source_seconds": 2},
    ])
    res = speed_ramp(str(ws_root), proj_rel, track=track, clip_index=0, keyframes=kfs)
    assert res["status"] == "success", res
    assert res["data"]["keyframe_format"] == "timemap"
    # source 0..2s at 0.5x over 100-frame clip -> 100 output frames
    assert res["data"]["expected_output_frames"] == 100


def test_tool_rejects_bad_keyframes(project_ws):
    ws_root, proj_rel, track = project_ws
    res = speed_ramp(str(ws_root), proj_rel, track=track, clip_index=0, keyframes="not json")
    assert res["status"] == "error"


def test_tool_rejects_bad_clip_index(project_ws):
    import json

    ws_root, proj_rel, track = project_ws
    kfs = json.dumps([{"at_seconds": 0, "speed": 2.0}])
    res = speed_ramp(str(ws_root), proj_rel, track=track, clip_index=99, keyframes=kfs)
    assert res["status"] == "error"
