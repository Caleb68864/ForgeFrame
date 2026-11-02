"""A scene-cut guide lands on the visible cut on the timeline, proven by melt."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import call_tool, make_hard_cut_clip, make_test_clip, requires_ffmpeg_ffprobe, requires_melt_ffmpeg
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.server.bundles.scene_guides import guide_add_scene_cuts
from workshop_video_brain.edit_mcp.server.tools import clips_nle, timeline_project, workspace_media
from ._oracle import frames_differ, melt_accepts, render_frame

pytestmark = [pytest.mark.external, requires_ffmpeg_ffprobe, requires_melt_ffmpeg]


def _workspace(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir()
    created = call_tool(workspace_media.workspace_create, title="Scene guides", media_root=str(media_root))
    assert created["status"] == "success", created
    workspace = Path(created["data"]["workspace_root"])
    assert call_tool(timeline_project.project_create_working_copy, str(workspace))["status"] == "success"
    return workspace


def test_guide_sits_on_the_timeline_cut_not_the_source_time(tmp_path, melt_bin, render_dir):
    workspace = _workspace(tmp_path)
    opener = make_test_clip(tmp_path / "opener.mp4", duration=1, kind="color", color="green")
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    for path in (opener, clip):
        assert call_tool(clips_nle.clip_insert, str(workspace), str(path))["status"] == "success"

    result = call_tool(guide_add_scene_cuts, str(workspace), str(clip), engine="ffmpeg")
    assert result["status"] == "success", result
    data = result["data"]
    assert data["guides_added"] == 1
    assert data["positions_frames"] == [75]  # 1 s opener + the 2 s cut, at 25 fps
    assert data["snapshot_id"]

    project_path = Path(data["project_file"])
    project = parse_project(project_path)
    assert [(g.position, g.label) for g in project.guides] == [(75, "Scene 1")]

    assert melt_accepts(project_path, melt_bin=melt_bin).ok
    before = render_frame(project_path, 74, render_dir, melt_bin=melt_bin, name="before.png")
    after = render_frame(project_path, 76, render_dir, melt_bin=melt_bin, name="after.png")
    assert frames_differ(before, after)


def test_source_not_on_the_timeline_writes_nothing(tmp_path):
    workspace = _workspace(tmp_path)
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    project_dir = workspace / "projects" / "working_copies"
    before = {path: path.stat().st_mtime_ns for path in project_dir.iterdir()}
    result = call_tool(guide_add_scene_cuts, str(workspace), str(clip), engine="ffmpeg")
    assert result["status"] == "success"
    assert result["data"]["guides_added"] == 0
    assert "note" in result["data"]
    assert {path: path.stat().st_mtime_ns for path in project_dir.iterdir()} == before


def test_corrupt_project_is_reported(tmp_path):
    workspace = _workspace(tmp_path)
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    corrupt = workspace / "projects" / "working_copies" / "bad_v99.kdenlive"
    corrupt.write_text("<mlt><truncated")
    result = call_tool(guide_add_scene_cuts, str(workspace), str(clip), project_file=str(corrupt))
    assert result["error_type"] == "corrupt_project"
