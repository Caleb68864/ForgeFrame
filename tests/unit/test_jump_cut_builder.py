"""The jump-cut builder and its argument validation; hermetic."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool
from workshop_video_brain.core.models.kdenlive import ProjectProfile
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import build_ranges_project, cut_guides
from workshop_video_brain.edit_mcp.server.bundles.jump_cut import timeline_build_jump_cut
from workshop_video_brain.workspace.manager import WorkspaceManager

PROFILE = ProjectProfile(width=320, height=180, fps=30.0, colorspace="709")
RANGES = [(0.0, 1.7), (3.3, 5.0)]


def _spans(playlist):
    return [(e.in_point, e.out_point) for e in playlist.entries]


def _starts(playlist):
    starts, frame = [], 0
    for entry in playlist.entries:
        starts.append(frame)
        frame += entry.out_point - entry.in_point + 1
    return starts


def test_half_open_ranges_become_inclusive_frames():
    project = build_ranges_project(Path("/m/a.mp4"), RANGES, profile=PROFILE)
    video, audio = project.playlists
    assert _spans(video) == [(0, 50), (99, 149)]
    assert _spans(audio) == _spans(video)
    assert _starts(video) == _starts(audio) == [0, 51]


def test_producer_length_covers_every_use():
    project = build_ranges_project(Path("/m/a.mp4"), RANGES, profile=PROFILE)
    assert int(project.producers[0].properties["length"]) >= 150
    longer = build_ranges_project(Path("/m/a.mp4"), RANGES, profile=PROFILE, source_frames=900)
    assert longer.producers[0].properties["length"] == "900"


def test_no_audio_means_no_audio_track():
    project = build_ranges_project(Path("/m/a.mp4"), RANGES, profile=PROFILE, has_audio=False)
    assert [t.track_type for t in project.tracks] == ["video"]
    assert len(project.playlists) == 1


def test_a_range_shorter_than_a_frame_is_skipped():
    project = build_ranges_project(Path("/m/a.mp4"), [(1.0, 1.001), (2.0, 3.0)], profile=PROFILE)
    assert _spans(project.playlists[0]) == [(60, 89)]


def test_cut_guides_sit_on_timeline_frames():
    project = build_ranges_project(Path("/m/a.mp4"), RANGES, profile=PROFILE)
    assert [(g.position, g.label) for g in cut_guides(project)] == [(51, "cut 1")]


@pytest.fixture
def workspace(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Jump", tmp_path, workspace_root=root)
    (root / "clip.mp4").write_bytes(b"not decoded")
    return root


def test_tool_is_registered():
    assert_registered("timeline_build_jump_cut")


def test_bad_json_is_reported(workspace):
    result = call_tool(timeline_build_jump_cut, str(workspace), "clip.mp4", keep_ranges_json="[[oops")
    assert result["status"] == "error"
    assert "keep_ranges_json" in result["message"]


@pytest.mark.parametrize(
    "ranges",
    ["[[3.0, 5.0], [0.0, 1.0]]", "[[2.0, 2.0]]", "[[3.0, 1.0]]", "[[-1.0, 1.0]]", "[[0.0, 2.0], [1.0, 3.0]]", "[]"],
    ids=["unsorted", "empty_span", "reversed", "negative", "overlap", "none"],
)
def test_invalid_ranges_are_refused(workspace, ranges):
    result = call_tool(timeline_build_jump_cut, str(workspace), "clip.mp4", keep_ranges_json=ranges)
    assert result["error_type"] == "invalid_input"


def test_missing_source(workspace):
    result = call_tool(timeline_build_jump_cut, str(workspace), "gone.mp4")
    assert result["error_type"] == "missing_file"


def test_unknown_engine(workspace):
    result = call_tool(timeline_build_jump_cut, str(workspace), "clip.mp4", engine="nope")
    assert result["error_type"] == "invalid_input"
