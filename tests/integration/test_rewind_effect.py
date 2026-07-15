"""ffmpeg-gated integration tests for the VHS rewind effect.

Builds a tiny testsrc clip with ffmpeg, runs the reverse pipeline, and asserts
via ffprobe that the reversed output has the expected duration. Also exercises
the full ``effect_rewind`` MCP tool end-to-end against a minimal Kdenlive
project.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    PlaylistEntry,
    Playlist,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import rewind as rw
from workshop_video_brain.edit_mcp.server.bundles import rewind as _bundle
from workshop_video_brain.workspace.manager import WorkspaceManager

# Under the project's pytest config, ``@mcp.tool()`` returns a FunctionTool
# wrapper (raw callable on ``.fn``); standalone it returns the plain function.
effect_rewind = getattr(_bundle.effect_rewind, "fn", _bundle.effect_rewind)

ffmpeg_available = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg/ffprobe not available on PATH"
)

FPS = 25
DURATION_S = 4


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _count_real_clips(project_path: Path, track: int) -> int:
    project = parse_project(project_path)
    playlist = project.playlists[track]
    return len([e for e in playlist.entries if e.producer_id])


def _make_testsrc(path: Path, with_audio: bool = False) -> None:
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc=size=320x240:rate={FPS}:duration={DURATION_S}"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION_S}", "-shortest"]
    cmd += ["-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Pipeline-level: reverse a real clip, assert duration
# ---------------------------------------------------------------------------

def test_reverse_pipeline_duration_video_only(tmp_path):
    src = tmp_path / "src.mp4"
    _make_testsrc(src)
    out = tmp_path / "reversed.mp4"

    args = rw.build_reverse_args(1.0, 3.0, 2.0, include_audio=False)
    result = run_ffmpeg(args, input_path=src, output_path=out, overwrite=True)
    assert result.success, result.stderr[-400:]
    assert out.exists()

    expected = rw.reversed_duration(1.0, 3.0, 2.0)  # 1.0s
    # Trim/encode boundaries add a frame or two; allow a small tolerance.
    assert abs(_probe_duration(out) - expected) <= 0.2


def test_reverse_pipeline_duration_with_audio(tmp_path):
    src = tmp_path / "src_av.mp4"
    _make_testsrc(src, with_audio=True)
    out = tmp_path / "reversed_av.mp4"

    args = rw.build_reverse_args(0.0, 6.0, 3.0, include_audio=True)
    # 6s window at 3x -> ~2s; source is only 4s so segment is clamped to 4s -> ~1.33s.
    result = run_ffmpeg(args, input_path=src, output_path=out, overwrite=True)
    assert result.success, result.stderr[-400:]
    # Output retains an audio stream (areverse + atempo chain ran).
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert len(json.loads(streams.stdout).get("streams", [])) == 1


# ---------------------------------------------------------------------------
# Full tool: effect_rewind end-to-end against a minimal project
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_ws(tmp_path):
    """Workspace + a minimal one-clip project pointing at a real testsrc file."""
    ws = WorkspaceManager.create(
        title="Rewind Test",
        media_root=str(tmp_path / "raw_media"),
        workspace_root=tmp_path / "workspace",
    )
    ws_root = Path(ws.workspace_root)
    raw_clip = ws_root / "media" / "raw" / "clip.mp4"
    raw_clip.parent.mkdir(parents=True, exist_ok=True)
    _make_testsrc(raw_clip)

    n_frames = FPS * DURATION_S
    project = KdenliveProject(
        title="Rewind Test",
        profile=ProjectProfile(width=320, height=240, fps=float(FPS)),
        producers=[Producer(
            id="clipsrc",
            resource=str(raw_clip),
            properties={"resource": str(raw_clip), "length": str(n_frames)},
        )],
        tracks=[Track(id="playlist0", track_type="video")],
        playlists=[Playlist(
            id="playlist0",
            entries=[PlaylistEntry(producer_id="clipsrc", in_point=0, out_point=n_frames - 1)],
        )],
    )
    proj_rel = "projects/working_copies/rewind.kdenlive"
    proj_path = ws_root / proj_rel
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    serialize_project(project, proj_path)

    # Locate the track index that actually holds the real clip after round-trip.
    reparsed = parse_project(proj_path)
    track = next(
        i for i, pl in enumerate(reparsed.playlists)
        if any(e.producer_id for e in pl.entries)
    )
    return ws_root, proj_rel, track


def test_effect_rewind_inserts_reversed_clip(project_ws):
    ws_root, proj_rel, track = project_ws
    before = _count_real_clips(ws_root / proj_rel, track)

    res = effect_rewind(
        str(ws_root), proj_rel, track=track, clip_index=0,
        start_seconds=1.0, end_seconds=3.0, speed=2.0, vhs_overlay=False,
    )

    assert res["status"] == "success", res
    data = res["data"]
    # Reversed media landed in media/processed, not media/raw.
    reversed_path = Path(data["reversed_media"])
    assert reversed_path.exists()
    assert "processed" in reversed_path.parts
    assert "raw" not in reversed_path.parts
    # Duration matches the reverse math.
    assert abs(_probe_duration(reversed_path) - data["expected_duration_seconds"]) <= 0.2
    # A new clip was inserted right after the original.
    assert data["new_clip_index"] == 1
    assert _count_real_clips(ws_root / proj_rel, track) == before + 1
    # A snapshot was taken before the write.
    assert data["snapshot_id"]

    # Source media in media/raw is untouched.
    raw_clip = ws_root / "media" / "raw" / "clip.mp4"
    assert raw_clip.exists()


def test_effect_rewind_rejects_bad_window(project_ws):
    ws_root, proj_rel, track = project_ws
    res = effect_rewind(
        str(ws_root), proj_rel, track=track, clip_index=0,
        start_seconds=3.0, end_seconds=1.0, vhs_overlay=False,
    )
    assert res["status"] == "error"


def test_effect_rewind_rejects_bad_clip_index(project_ws):
    ws_root, proj_rel, track = project_ws
    res = effect_rewind(
        str(ws_root), proj_rel, track=track, clip_index=99,
        start_seconds=1.0, end_seconds=3.0, vhs_overlay=False,
    )
    assert res["status"] == "error"


def test_effect_rewind_with_vhs_overlay_is_best_effort(project_ws):
    ws_root, proj_rel, track = project_ws
    res = effect_rewind(
        str(ws_root), proj_rel, track=track, clip_index=0,
        start_seconds=1.0, end_seconds=3.0, speed=2.0, vhs_overlay=True,
    )
    # Overlay is best-effort: the tool still succeeds and reports what applied.
    assert res["status"] == "success", res
    data = res["data"]
    assert data["vhs_overlay"] is True
    assert isinstance(data["effects_applied"], list)
    assert isinstance(data["overlay_errors"], list)
