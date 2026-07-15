"""External render proof for the multicam tools (Phases A2 + B).

Shells out to real ``ffmpeg`` (angle synthesis + audio sync), ``melt`` and
``ffprobe`` (skipped when absent).  Two synthetic "angles" -- distinct solid
colours, angle B time-shifted by a known offset and carrying the same audio
event pattern -- exercise the full workflow against decoded pixels:

* **assemble** -- ``multicam_assemble`` recovers B's +2.0 s offset by audio and
  stacks each angle on its own synced track.  We assert the recovered offset, the
  per-track leading-gap positioning in the re-parsed project, and that a rendered
  frame shows each track in its correct place (the delayed reference is absent
  where its gap says it should be, and present past the point the other angle
  ends).

* **switch** -- ``multicam_switch`` at t=2.0 s builds a program track whose frame
  *before* the cut is angle A's colour and *after* the cut is angle B's colour.

Projects/producers are real media files, so melt loads them via avformat.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server import tools as _tools_mod  # noqa: F401
import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401 (auto-registers)
from workshop_video_brain.edit_mcp.server.bundles import multicam as _mc_mod

from ._oracle import melt_accepts, mean_color, render_frame

pytestmark = pytest.mark.external

FPS = 25.0
W, H = 320, 180
DUR = 5.0                       # seconds per angle => 125 frames
LEN_FRAMES = int(round(DUR * FPS))
KNOWN_OFFSET = 2.0              # angle B starts 2.0 s of event later than A


def _fn(tool):
    return getattr(tool, "fn", tool)


workspace_create = _fn(getattr(_tools_mod, "workspace_create"))
multicam_assemble = _fn(_mc_mod.multicam_assemble)
multicam_switch = _fn(_mc_mod.multicam_switch)


def _dominant(png) -> str:
    r, g, b = mean_color(png)
    if r > 120 and g < 90 and b < 90:
        return "red"
    if b > 120 and r < 90 and g < 90:
        return "blue"
    return f"other(r={r:.0f},g={g:.0f},b={b:.0f})"


def _make_angle(ffmpeg_bin: str, path: Path, color: str, lead: float) -> None:
    """Render an angle: a solid-*color* video + a shared burst pattern shifted by *lead*."""
    bursts = [(0.5, 440), (1.5, 880), (2.4, 330)]
    terms = []
    for start, freq in bursts:
        t0 = start + lead
        terms.append(f"0.6*sin(2*PI*{freq}*t)*(between(t,{t0:.3f},{t0 + 0.3:.3f}))")
    expr = "+".join(terms)
    cmd = [
        ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={int(FPS)}:d={DUR}",
        "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={DUR}",
        "-map", "0:v", "-map", "1:a",
        "-ac", "1", "-ar", "44100", "-pix_fmt", "yuv420p",
        "-t", str(DUR), str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _make_ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Multicam Render", media_root=str(media_root))
    assert result["status"] == "success", result
    return Path(result["data"]["workspace_root"])


def _base_project(path: Path) -> None:
    """A minimal project: profile + an empty audio track + tractor (no video yet)."""
    p = KdenliveProject(
        version="7", title="multicam",
        profile=ProjectProfile(width=W, height=H, fps=FPS, colorspace="709"),
    )
    p.tracks = [Track(id="a1", track_type="audio", name="Audio")]
    p.playlists = [Playlist(id="a1", entries=[])]
    p.tractor = {"id": "tractor0", "in": "0", "out": "0"}
    serialize_project(p, path)


def _angles(ws: Path, ffmpeg_bin: str) -> tuple[Path, Path]:
    raw = ws / "media" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    a = raw / "angleA_red.mp4"
    b = raw / "angleB_blue.mp4"
    _make_angle(ffmpeg_bin, a, "red", lead=0.0)               # reference
    _make_angle(ffmpeg_bin, b, "blue", lead=KNOWN_OFFSET)     # +2.0 s later
    return a, b


# ---------------------------------------------------------------------------
# Phase A2 -- assemble: audio-synced stacked placement
# ---------------------------------------------------------------------------

def test_multicam_assemble_syncs_and_positions_angles(
    ffmpeg_bin, melt_bin, ffprobe_bin, tmp_path: Path
):
    ws = _make_ws(tmp_path)
    a, b = _angles(ws, ffmpeg_bin)
    proj_rel = "multicam.kdenlive"
    _base_project(ws / proj_rel)

    out = multicam_assemble(
        workspace_path=str(ws), project_file=proj_rel,
        sources=f"{a},{b}", reference=0, sync="audio",
    )
    assert out["status"] == "success", out
    angles = out["data"]["angles"]
    assert len(angles) == 2

    # Recovered offset for angle B is ~ +2.0 s (event later into B).
    ang_b = next(x for x in angles if x["angle"] == 1)
    assert abs(ang_b["offset_seconds"] - KNOWN_OFFSET) <= 0.15, angles
    # Alignment => reference (RED) carries a ~50-frame lead gap, B (BLUE) gap 0.
    ang_a = next(x for x in angles if x["angle"] == 0)
    assert abs(ang_a["gap_frames"] - 50) <= 4, angles
    assert ang_b["gap_frames"] == 0, angles

    # Positional truth in the re-parsed project: RED track leads with a blank of
    # its gap; BLUE track opens directly on its clip.
    project = parse_project(ws / proj_rel)
    by_id = {pl.id: pl for pl in project.playlists}
    red_pl = by_id[ang_a["playlist_id"]]
    blue_pl = by_id[ang_b["playlist_id"]]
    assert red_pl.entries[0].producer_id == ""                       # leading blank
    assert red_pl.entries[0].out_point + 1 == ang_a["gap_frames"]
    assert blue_pl.entries[0].producer_id != ""                      # clip at frame 0

    # melt accepts the stacked project.
    assert melt_accepts(ws / proj_rel, melt_bin=melt_bin, frames=30).ok

    # Pixel positioning: BLUE (top) spans [0,125); RED (bottom) spans [50,175).
    #  * frame 25 -> only BLUE present (RED still inside its 50-frame gap) => blue
    #  * frame 150 -> BLUE has ended, RED present => red (proves RED's +50 offset)
    rd = ws / "renders"
    assert _dominant(render_frame(ws / proj_rel, 25, rd, melt_bin=melt_bin, name="mc_a25.png")) == "blue"
    assert _dominant(render_frame(ws / proj_rel, 150, rd, melt_bin=melt_bin, name="mc_a150.png")) == "red"


# ---------------------------------------------------------------------------
# Phase B -- switch: program feed before/after a cut
# ---------------------------------------------------------------------------

def _stacked_project(path: Path, a: Path, b: Path) -> None:
    """Two full-span angle tracks (RED bottom, BLUE top) + audio, from real media."""
    def _prod(pid: str, resource: Path) -> Producer:
        return Producer(id=pid, resource=str(resource), properties={"resource": str(resource)})

    p = KdenliveProject(
        version="7", title="stacked",
        profile=ProjectProfile(width=W, height=H, fps=FPS, colorspace="709"),
    )
    p.producers = [_prod("angleA", a), _prod("angleB", b)]
    p.tracks = [
        Track(id="angle0", track_type="video", name="Angle 0"),
        Track(id="angle1", track_type="video", name="Angle 1"),
        Track(id="a1", track_type="audio", name="Audio"),
    ]
    p.playlists = [
        Playlist(id="angle0", entries=[PlaylistEntry(producer_id="angleA", in_point=0, out_point=LEN_FRAMES - 1)]),
        Playlist(id="angle1", entries=[PlaylistEntry(producer_id="angleB", in_point=0, out_point=LEN_FRAMES - 1)]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(LEN_FRAMES - 1)}
    serialize_project(p, path)


def test_multicam_switch_program_feed_before_and_after_cut(
    ffmpeg_bin, melt_bin, tmp_path: Path
):
    ws = _make_ws(tmp_path)
    a, b = _angles(ws, ffmpeg_bin)
    proj_rel = "stacked.kdenlive"
    _stacked_project(ws / proj_rel, a, b)

    # Show angle 0 (RED) from 0 s, switch to angle 1 (BLUE) at t=2.0 s.
    out = multicam_switch(
        workspace_path=str(ws), project_file=proj_rel,
        cuts='[{"at_seconds": 0.0, "angle": 0}, {"at_seconds": 2.0, "angle": 1}]',
    )
    assert out["status"] == "success", out
    segs = out["data"]["segments"]
    assert len(segs) == 2
    assert segs[0]["angle"] == 0 and segs[0]["start_frame"] == 0 and segs[0]["end_frame"] == 50
    assert segs[1]["angle"] == 1 and segs[1]["start_frame"] == 50

    assert melt_accepts(ws / proj_rel, melt_bin=melt_bin, frames=30).ok

    # Program track (top) shows RED before the cut, BLUE after it.
    rd = ws / "renders"
    before = render_frame(ws / proj_rel, 40, rd, melt_bin=melt_bin, name="mc_sw_before.png")   # 1.6 s
    after = render_frame(ws / proj_rel, 70, rd, melt_bin=melt_bin, name="mc_sw_after.png")     # 2.8 s
    assert _dominant(before) == "red", "before the t=2s cut the program should be angle A (red)"
    assert _dominant(after) == "blue", "after the t=2s cut the program should be angle B (blue)"
