"""Workspace undo/redo journal (prompt 17): project_undo / project_redo / project_history."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from tests._testkit import call_tool, sequence_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
    serialize_versioned,
)
from workshop_video_brain.edit_mcp.server.tools.clips_nle import clip_move, track_add
from workshop_video_brain.edit_mcp.server.tools.effects_catalog import effect_add
from workshop_video_brain.edit_mcp.server.tools.history import (
    project_history,
    project_redo,
    project_undo,
)
from workshop_video_brain.workspace import jobs, undo
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest
from workshop_video_brain.workspace.snapshot import restore


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Undo Test", tmp_path, workspace_root=root)
    # Seed under the manifest slug, as the tools write: a different stem made
    # the first tool write <slug>_v1 beside project_v1, and "latest" between
    # two _v1 files fell back to mtime -- equal on a fast CI runner.
    serialize_versioned(sequence_project(), root, read_manifest(root).slug)
    # The seeding write is journaled too; start every test from an empty stack.
    undo.journal_path(root).unlink()
    return root


def _wc(root: Path) -> list[str]:
    return sorted(p.name for p in (root / "projects" / "working_copies").glob("*.kdenlive"))


def _latest(root: Path) -> Path:
    from workshop_video_brain.edit_mcp.server.tools_helpers._projects import latest_project
    return latest_project((root / "projects" / "working_copies").glob("*.kdenlive"))


def _ok(result: dict) -> dict:
    assert result["status"] == "success", result
    return result["data"]


def test_undo_create_moves_version_to_trash_and_redo_restores_it(ws):
    v1 = _latest(ws)
    data = _ok(call_tool(track_add, str(ws)))
    v2 = Path(data["kdenlive_path"])
    v2_bytes = v2.read_bytes()
    assert _wc(ws) == sorted([v1.name, v2.name])

    undone = _ok(call_tool(project_undo, str(ws)))
    assert undone["undone"][0]["label"] == "track_add"
    assert _wc(ws) == [v1.name]
    assert undone["latest_project"] == str(v1)
    trashed = list((ws / "projects" / "undo" / "trash").iterdir())
    assert len(trashed) == 1 and trashed[0].name.endswith(v2.name)
    assert trashed[0].read_bytes() == v2_bytes

    _ok(call_tool(project_redo, str(ws)))
    assert v2.read_bytes() == v2_bytes
    assert _latest(ws) == v2


def test_undo_in_place_write_restores_bytes_and_redo_reapplies(ws):
    latest = _latest(ws)
    before = latest.read_bytes()
    _ok(call_tool(effect_add, str(ws), str(latest), 0, 0, "brightness",
                  allow_unregistered=True))
    after = latest.read_bytes()
    assert after != before

    _ok(call_tool(project_undo, str(ws)))
    assert latest.read_bytes() == before
    _ok(call_tool(project_redo, str(ws)))
    assert latest.read_bytes() == after
    # And the redo is undoable again.
    _ok(call_tool(project_undo, str(ws)))
    assert latest.read_bytes() == before


def test_new_edit_after_undo_clears_redo(ws):
    _ok(call_tool(track_add, str(ws)))
    _ok(call_tool(project_undo, str(ws)))
    _ok(call_tool(track_add, str(ws), "audio"))
    result = call_tool(project_redo, str(ws))
    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert "Nothing to redo" in result["message"]


def test_hand_edit_after_tool_write_is_a_conflict_and_changes_nothing(ws):
    v2 = Path(_ok(call_tool(track_add, str(ws)))["kdenlive_path"])
    v2.write_bytes(v2.read_bytes() + b"\n<!-- saved in Kdenlive -->\n")
    listing, edited = _wc(ws), v2.read_bytes()
    journal = undo.journal_path(ws).read_bytes()

    result = call_tool(project_undo, str(ws))

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert "changed outside ForgeFrame" in result["message"]
    assert v2.name in result["message"]
    assert _wc(ws) == listing and v2.read_bytes() == edited
    assert undo.journal_path(ws).read_bytes() == journal


def test_nothing_to_undo_and_bad_steps(ws):
    result = call_tool(project_undo, str(ws))
    assert result["error_type"] == "invalid_input" and "Nothing to undo" in result["message"]
    result = call_tool(project_undo, str(ws), 0)
    assert result["error_type"] == "invalid_input"


def test_multi_step_undo_and_history(ws):
    v1 = _latest(ws)
    _ok(call_tool(track_add, str(ws)))
    _ok(call_tool(clip_move, str(ws), 0, 1))
    hist = _ok(call_tool(project_history, str(ws)))
    assert [h["label"] for h in hist["undo"]] == ["clip_move", "track_add"]
    assert hist["redo"] == []

    undone = _ok(call_tool(project_undo, str(ws), 2))
    assert [u["label"] for u in undone["undone"]] == ["clip_move", "track_add"]
    assert _wc(ws) == [v1.name]
    hist = _ok(call_tool(project_history, str(ws)))
    assert hist["undo"] == []
    assert [h["label"] for h in hist["redo"]] == ["track_add", "clip_move"]


def test_active_job_blocks_undo(ws, monkeypatch):
    _ok(call_tool(track_add, str(ws)))
    record = dict(id=str(uuid4()), operation="render", parameters={}, status="running",
                  created_at=time.time(), updated_at=time.time(), pid=12345,
                  outputs=[], error="", progress={})
    with jobs._db(ws) as connection:
        jobs._save(connection, record)
    monkeypatch.setattr(jobs, "_worker_alive", lambda r: True)
    listing = _wc(ws)

    result = call_tool(project_undo, str(ws))

    assert result["status"] == "error"
    assert "running" in result["message"] and "sha256" in result["message"]
    assert _wc(ws) == listing

    # A dead worker's leftover "running" record does not block for ever.
    monkeypatch.setattr(jobs, "_worker_alive", lambda r: False)
    _ok(call_tool(project_undo, str(ws)))


def test_concurrent_tool_writes_lose_no_journal_entry(ws):
    errors: list = []
    paths: list = []
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait()
            paths.append(_ok(call_tool(track_add, str(ws)))["kdenlive_path"])
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors
    assert len(set(paths)) == 2
    assert undo.depth(ws) == 2
    data = json.loads(undo.journal_path(ws).read_text())
    assert sorted(Path(e["path"]).name for e in data["undo"]) == sorted(Path(p).name for p in paths)


def test_cap_keeps_newest_fifty_groups(ws):
    latest = _latest(ws)
    for i in range(55):
        with undo.edit_group(f"edit{i}"):
            undo.record_write(ws, latest, "create", None, f"{i}".encode())
    assert undo.depth(ws) == 50
    labels = [h["label"] for h in undo.history(ws, 100)["undo"]]
    assert labels[0] == "edit54" and labels[-1] == "edit5"


def test_writes_outside_a_workspace_are_not_journaled(tmp_path):
    out = tmp_path / "loose.kdenlive"
    serialize_project(sequence_project(), out)
    serialize_project(sequence_project(), out)
    assert not (tmp_path / "projects" / "undo").exists()


def test_snapshot_restore_is_undoable(ws):
    latest = _latest(ws)
    original = latest.read_bytes()
    _ok(call_tool(effect_add, str(ws), str(latest), 0, 0, "brightness",
                  allow_unregistered=True))
    edited = latest.read_bytes()
    snap_id = json.loads(undo.journal_path(ws).read_text())["undo"][-1]["before_snapshot_id"]

    restore(ws, snap_id)
    assert latest.read_bytes() == original
    assert undo.history(ws)["undo"][0]["label"] == f"snapshot_restore:{snap_id}"

    undo.undo(ws)
    assert latest.read_bytes() == edited


def test_one_tool_writing_the_same_file_twice_undoes_as_one_step(ws):
    latest = _latest(ws)
    before = latest.read_bytes()
    project = sequence_project(colors=["0xff00ffff"])
    with undo.edit_group("double_write"):
        serialize_project(project, latest)
        serialize_project(sequence_project(colors=["0x00ff00ff"]), latest)
    assert undo.depth(ws) == 1
    undo.undo(ws)
    assert latest.read_bytes() == before
    undo.redo(ws)
    undo.undo(ws)
    assert latest.read_bytes() == before
