"""Real melt: cuts land on beats, flashes brighten beat frames, zooms punch (prompt 23)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tests._testkit import call_tool, make_test_clip, requires_ffmpeg, sequence_project
from workshop_video_brain.core.models.kdenlive import Producer
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_start_frame
from workshop_video_brain.edit_mcp.server.bundles.beat_grid import music_beat_grid
from workshop_video_brain.edit_mcp.server.bundles.beat_sync import beat_cut, beat_flash, beat_zoom
from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest

from . import builders
from ._oracle import frames_differ, frames_similar, mean_color, render_frame

pytestmark = pytest.mark.external

BEATS = [round(0.48 * i, 2) for i in range(1, 25)]  # 12 frames apart at 25 fps


def _workspace(tmp_path: Path, project, beats=BEATS) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Beats", tmp_path, workspace_root=root)
    serialize_versioned(project, root, read_manifest(root).slug)
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "beat_grid.json").write_text(json.dumps({"bpm_estimate": 125.0, "beats": beats,
                                                                 "source": ""}))
    return root


def _latest(root: Path) -> Path:
    return latest_project((root / "projects" / "working_copies").glob("*.kdenlive"))


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def _dominant(png) -> str:
    r, g, b = mean_color(png)
    return max((("red", r), ("green", g), ("blue", b)), key=lambda kv: kv[1])[0]


def test_cuts_land_on_beats(melt_bin, tmp_path, render_dir):
    project = sequence_project([builders.RED, builders.GREEN, builders.BLUE, builders.RED], frames_each=20)
    for p in project.producers:
        p.properties["length"] = "200"
    root = _workspace(tmp_path, project)
    data = _ok(call_tool(beat_cut, str(root), intensity="medium", music_offset_seconds=0.0))
    path = _latest(root)
    video = parse_project(path).playlists[0]
    colours = ["red", "green", "blue", "red"]
    for k in range(1, 4):
        cut = clip_start_frame(video.entries, k)
        assert cut in data["beat_frames"], (cut, data["beat_frames"])
        before = render_frame(path, cut - 1, render_dir, melt_bin=melt_bin, name=f"cut{k}_before.png")
        after = render_frame(path, cut, render_dir, melt_bin=melt_bin, name=f"cut{k}_after.png")
        assert (_dominant(before), _dominant(after)) == (colours[k - 1], colours[k])


def _luma(png) -> float:
    r, g, b = mean_color(png)
    return 0.299 * r + 0.587 * g + 0.114 * b


def test_flash_brightens_beat_frames(melt_bin, tmp_path, render_dir):
    root = _workspace(tmp_path, sequence_project(["0x808080ff"], frames_each=100))
    data = _ok(call_tool(beat_flash, str(root), every_n=1, music_offset_seconds=0.0, strength=1.0))
    path = _latest(root)
    beat = data["beat_frames"][2]
    on = _luma(render_frame(path, beat, render_dir, melt_bin=melt_bin, name="flash_on.png"))
    off = _luma(render_frame(path, beat + 6, render_dir, melt_bin=melt_bin, name="flash_off.png"))
    assert on > off + 40, (on, off)


@requires_ffmpeg
def test_zoom_punches_on_the_beat(melt_bin, tmp_path, render_dir):
    clip = make_test_clip(tmp_path / "bars.mp4", duration=4.0, size=(320, 180))
    project = sequence_project(["0x000000ff"], frames_each=100)
    project.producers[0] = Producer(id="producer_0", resource=str(clip), properties={
        "resource": str(clip), "mlt_service": "avformat", "length": "100"})
    root = _workspace(tmp_path, project, beats=[0.96])  # one beat at frame 24
    plain = _latest(root)
    plain_peak = render_frame(plain, 24, render_dir, melt_bin=melt_bin, name="plain24.png")
    plain_after = render_frame(plain, 50, render_dir, melt_bin=melt_bin, name="plain50.png")
    _ok(call_tool(beat_zoom, str(root), every_n=1, music_offset_seconds=0.0, punch=0.25))
    path = _latest(root)
    assert frames_differ(plain_peak, render_frame(path, 24, render_dir, melt_bin=melt_bin, name="zoom24.png"))
    assert frames_similar(plain_after, render_frame(path, 50, render_dir, melt_bin=melt_bin, name="zoom50.png"))


@requires_ffmpeg
def test_end_to_end_from_a_click_track(melt_bin, tmp_path, render_dir):
    click = tmp_path / "click.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='if(lt(mod(t\\,0.5)\\,0.03)\\,sin(2*PI*1000*t)\\,0)':s=44100:d=8",
                    str(click)], check=True, capture_output=True, timeout=60)
    project = sequence_project([builders.RED, builders.GREEN, builders.BLUE, builders.RED, builders.GREEN],
                               frames_each=20)
    for p in project.producers:
        p.properties["length"] = "300"
    root = _workspace(tmp_path, project)
    grid = _ok(call_tool(music_beat_grid, str(root), str(click)))
    assert abs(grid["bpm_estimate"] - 120) <= 2, grid["bpm_estimate"]
    data = _ok(call_tool(beat_cut, str(root), every_n=1, music_offset_seconds=0.0))
    video = parse_project(_latest(root)).playlists[0]
    for k in range(1, 5):
        cut = clip_start_frame(video.entries, k)
        nearest = round(cut / 12.5) * 12.5  # multiples of 0.5 s at 25 fps
        assert abs(cut - nearest) <= 1, (cut, data["beat_frames"])
    with Image.open(render_frame(_latest(root), 0, render_dir, melt_bin=melt_bin, name="e2e.png")) as image:
        assert image.size[0] > 0
