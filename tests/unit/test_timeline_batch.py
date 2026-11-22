"""timeline_batch (prompt 17): all operations, or none."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, sequence_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.server.tools.history import project_undo, timeline_batch
from workshop_video_brain.workspace import undo
from workshop_video_brain.workspace.manager import WorkspaceManager


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    manifest = WorkspaceManager.create("Batch Test", tmp_path, workspace_root=root)
    serialize_versioned(sequence_project(), root, getattr(manifest, "slug", None) or "project")
    undo.journal_path(root).unlink()
    return root


def _wc(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (root / "projects" / "working_copies").glob("*.kdenlive")}


def _batch(ws: Path, ops, **kw) -> dict:
    return call_tool(timeline_batch, str(ws), json.dumps(ops), **kw)


def test_tools_registered():
    assert_registered("project_undo", "project_redo", "project_history", "timeline_batch")


def test_failed_batch_rolls_everything_back(ws):
    before = _wc(ws)
    start = undo.depth(ws)

    result = _batch(ws, [
        {"tool": "track_add", "args": {"track_type": "video"}},
        {"tool": "clip_remove", "args": {"clip_index": 99}},
    ])

    assert result["status"] == "error", result
    assert result["failed_at_index"] == 1
    assert result["tool"] == "clip_remove"
    assert result["rolled_back"] is True
    assert result["completed_before_failure"] == 1
    assert result["inner_error"]["status"] == "error"
    assert _wc(ws) == before
    assert undo.depth(ws) == start
    assert undo.history(ws)["redo"] == []
    # The intermediate version is kept in trash, not deleted.
    assert len(list((ws / "projects" / "undo" / "trash").iterdir())) == 1


def test_successful_batch_is_one_undo_step(ws):
    before = _wc(ws)
    result = _batch(ws, [
        {"tool": "track_add", "args": {}},
        {"tool": "track_add", "args": {"track_type": "audio"}},
    ])
    data = result["data"]
    assert result["status"] == "success", result
    assert data["count"] == 2
    assert len(_wc(ws)) == len(before) + 2
    assert undo.depth(ws) == 1

    undone = call_tool(project_undo, str(ws))
    assert undone["status"] == "success", undone
    assert undone["data"]["undone"][0]["label"] == "timeline_batch"
    assert _wc(ws) == before


@pytest.mark.parametrize("ops, needle", [
    ([{"tool": "no_such_tool", "args": {}}], "unknown tool"),
    ([{"tool": "project_undo", "args": {}}], "cannot run inside a batch"),
    ([{"tool": "render_preview", "args": {}}], "cannot run inside a batch"),
    ([{"tool": "job_cancel", "args": {}}], "cannot run inside a batch"),
    ([{"tool": "track_add", "args": {"workspace_path": "/elsewhere"}}], "not this batch's workspace"),
    ([{"tool": "track_add", "args": {"colour": "red"}}], "has no parameter"),
    ([{"tool": "track_add", "args": []}], "args must be an object"),
    ([{"tool": "media_check_vfr", "args": {}}, {"tool": "nope", "args": {}}], "unknown tool"),
    ([], "non-empty JSON array"),
])
def test_validation_fails_before_any_write(ws, ops, needle):
    # A valid first operation must not run when a later one is invalid.
    ops = [{"tool": "track_add", "args": {}}, *ops] if ops else ops
    before = _wc(ws)
    result = _batch(ws, ops)
    assert result["status"] == "error"
    assert needle in result["message"], result
    assert _wc(ws) == before
    assert not undo.journal_path(ws).exists()


def test_bad_json(ws):
    result = call_tool(timeline_batch, str(ws), "[{not json")
    assert result["error_type"] == "bad_json_param"


def test_tool_without_workspace_first_is_refused(ws):
    result = _batch(ws, [{"tool": "gif_render", "args": {}}])
    assert result["status"] == "error"
    assert "workspace_path first" in result["message"]


def test_dry_run_returns_plan_and_writes_nothing(ws):
    before = _wc(ws)
    result = _batch(ws, [{"tool": "track_add", "args": {"track_type": "audio"}}], dry_run=True)
    assert result["status"] == "success", result
    plan = result["data"]["plan"]
    assert plan == [{"tool": "track_add",
                     "args": {"track_type": "audio", "workspace_path": str(ws.resolve())}}]
    assert _wc(ws) == before


def test_batch_needs_a_real_workspace(tmp_path):
    result = call_tool(timeline_batch, str(tmp_path), json.dumps([{"tool": "track_add"}]))
    assert result["status"] == "error"
    assert "workspace.yaml" in result["message"]
