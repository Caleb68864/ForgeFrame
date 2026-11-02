"""Thumbnails come from the composited timeline, by either engine."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tests._testkit import (
    call_tool,
    color_producer,
    make_test_clip,
    requires_melt,
    requires_mlt_bindings,
    two_track_project,
)
from tests.integration.external._oracle import frame_delta
from workshop_video_brain.core.models.kdenlive import PlaylistEntry
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.mlt import engine
from workshop_video_brain.edit_mcp.server.bundles.timeline_thumbnails import timeline_thumbnails
from workshop_video_brain.workspace.manager import WorkspaceManager


def _workspace(tmp_path: Path, project) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Thumbs", tmp_path, workspace_root=root)
    working = root / "projects" / "working_copies"
    working.mkdir(parents=True, exist_ok=True)
    serialize_project(project, working / "thumbs_v1.kdenlive")
    return root


def _red_with_blue_on_top():
    project = two_track_project()
    project.producers.append(color_producer("blue", "0x0000ffff", 200))
    project.playlists[1].entries = [
        PlaylistEntry(producer_id="", in_point=0, out_point=19),
        PlaylistEntry(producer_id="blue", in_point=0, out_point=9),
    ]
    return project


def _center(path: str) -> tuple[int, int, int]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return rgb.getpixel((rgb.width // 2, rgb.height // 2))


def _assert_colors(frames: list[dict]) -> None:
    by_frame = {item["frame"]: _center(item["path"]) for item in frames}
    for frame, expected in ((5, (255, 0, 0)), (25, (0, 0, 255)), (45, (255, 0, 0))):
        assert all(abs(got - want) <= 20 for got, want in zip(by_frame[frame], expected)), (frame, by_frame[frame])


@requires_mlt_bindings
def test_bindings_grab_the_composite(tmp_path):
    root = _workspace(tmp_path, _red_with_blue_on_top())
    result = call_tool(timeline_thumbnails, str(root), frames="5,25,45", width=64)
    assert result["status"] == "success", result
    assert result["data"]["engine"] == "bindings"
    _assert_colors(result["data"]["frames"])
    assert Path(result["data"]["output_dir"]).is_relative_to(root / "reports" / "timeline_frames")
    with Image.open(result["data"]["frames"][0]["path"]) as image:
        assert image.size == (64, 36)


@requires_mlt_bindings
def test_bindings_clamp_past_the_end(tmp_path):
    root = _workspace(tmp_path, _red_with_blue_on_top())
    result = call_tool(timeline_thumbnails, str(root), frames="100000", width=32)
    assert result["status"] == "success", result
    item = result["data"]["frames"][0]
    assert item["requested"] == 100000
    assert item["frame"] < 100000


@requires_melt
def test_melt_fallback_grabs_the_composite(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    root = _workspace(tmp_path, _red_with_blue_on_top())
    result = call_tool(timeline_thumbnails, str(root), frames="5,25,45", width=64)
    assert result["status"] == "success", result
    assert result["data"]["engine"] == "melt"
    _assert_colors(result["data"]["frames"])


@requires_melt
def test_melt_fallback_is_not_pillarboxed(tmp_path, monkeypatch):
    """Passing width= and height= to melt renders through its default profile, with black bars."""
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    root = _workspace(tmp_path, two_track_project())
    result = call_tool(timeline_thumbnails, str(root), frames="5", width=64)
    with Image.open(result["data"]["frames"][0]["path"]) as image:
        red, green, blue = image.convert("RGB").getpixel((0, 18))
    assert red > 200 and green < 40 and blue < 40


@requires_melt
def test_times_convert_at_the_project_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    root = _workspace(tmp_path, _red_with_blue_on_top())
    result = call_tool(timeline_thumbnails, str(root), times="1.0", width=32)
    assert result["status"] == "success", result
    assert result["data"]["frames"][0]["frame"] == 25


@requires_melt
@requires_mlt_bindings
def test_title_composite_matches_the_slow_melt_method(tmp_path):
    from workshop_video_brain.edit_mcp.server.bundles.titles import title_card_add

    project = two_track_project()
    root = _workspace(tmp_path, project)
    path = root / "projects" / "working_copies" / "thumbs_v1.kdenlive"
    added = call_tool(title_card_add, str(path), "HELLO WORLD", subtitle="Check", at_seconds=0.0, duration_seconds=2.0)
    assert added["status"] == "success", added

    frame = 15
    grabbed = call_tool(timeline_thumbnails, str(root), project_file=str(path), frames=str(frame), width=project.profile.width)
    assert grabbed["status"] == "success", grabbed
    fast = grabbed["data"]["frames"][0]["path"]

    old_dir = tmp_path / "old"
    old_dir.mkdir()
    subprocess.run(
        ["melt", str(path), f"out={frame}", "-consumer", f"avformat:{old_dir}/f_%05d.png",
         "vcodec=png", "an=1", "terminate_on_pause=1"],
        check=True, capture_output=True, timeout=120,
    )
    slow = sorted(old_dir.glob("f_*.png"))[-1]
    assert frame_delta(fast, slow) <= 3


@requires_melt
def test_missing_media_is_an_error_with_no_png(tmp_path):
    clip = make_test_clip(tmp_path / "gone.mp4", duration=1)
    project = two_track_project()
    project.producers[0].resource = str(clip)
    project.producers[0].properties = {"resource": str(clip), "mlt_service": "avformat", "length": "25"}
    project.playlists[0].entries[0].out_point = 24
    root = _workspace(tmp_path, project)
    clip.unlink()
    result = call_tool(timeline_thumbnails, str(root), frames="5", width=64)
    assert result["error_type"] == "missing_file"
    assert not list((root / "reports").rglob("*.png"))


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [({}, "invalid_input"),
     ({"times": "1", "frames": "1"}, "invalid_input"),
     ({"frames": "1", "width": 8}, "invalid_input"),
     ({"frames": "1", "width": 4000}, "invalid_input"),
     ({"frames": "abc"}, "invalid_input"),
     ({"times": "nan"}, "invalid_input"),
     ({"frames": "-1"}, "invalid_index")],
)
def test_arguments_are_validated(tmp_path, kwargs, error_type):
    root = _workspace(tmp_path, two_track_project())
    assert call_tool(timeline_thumbnails, str(root), **kwargs)["error_type"] == error_type


def test_corrupt_project_is_reported(tmp_path):
    root = _workspace(tmp_path, two_track_project())
    bad = root / "projects" / "working_copies" / "bad_v9.kdenlive"
    bad.write_text("<mlt><oops")
    assert call_tool(timeline_thumbnails, str(root), frames="1")["error_type"] == "corrupt_project"
