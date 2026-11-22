"""snapshot_diff tool: version refs, read-only, errors (prompt 22)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, sequence_project
from workshop_video_brain.core.models.timeline import AddEffect, AddGuide
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.server.bundles.snapshot_diff import snapshot_diff
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest
from workshop_video_brain.workspace.snapshot import create as create_snapshot

R, B = "0xff0000ff", "0x0000ffff"


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Diff", tmp_path, workspace_root=root)
    slug = read_manifest(root).slug
    v1 = sequence_project([R, B])
    path_v1 = serialize_versioned(v1, root, slug)
    create_snapshot(root, path_v1, "before the edit")
    v2 = patch_project(v1, [AddEffect(track_index=0, clip_index=1, effect_name="avfilter.negate"),
                            AddGuide(position_frames=25, label="Blue starts")])
    v2.playlists[0].entries[0] = v2.playlists[0].entries[0].model_copy(update={"in_point": 5})
    serialize_versioned(v2, root, slug)
    return root


def _files(root: Path) -> dict[str, float]:
    return {str(p.relative_to(root)): p.stat().st_mtime for p in root.rglob("*") if p.is_file()}


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("snapshot_diff")


def test_previous_to_latest_is_read_only(ws):
    before = _files(ws)
    data = _ok(call_tool(snapshot_diff, str(ws)))
    assert _files(ws) == before
    assert data["a"].endswith("_v1.kdenlive") and data["b"].endswith("_v2.kdenlive")
    assert not data["identical"]
    lines = data["text"].splitlines()
    # The trim shortens clip 0, so the blue clip after it moves 5 frames earlier.
    assert lines[0] == "2 clips changed on V1 (Video), 1 effect added, 1 guide added."
    assert any("moved from 0:01 [25] to 0:00 [20]" in line for line in lines)
    assert any("trimmed (in +5 frames" in line for line in lines)
    assert any("avfilter.negate added" in line for line in lines)
    assert any("Guide 'Blue starts' added at 0:01 [25]" in line for line in lines)


def test_snapshot_id_and_relative_path(ws):
    snap_id = next((ws / "projects" / "snapshots").iterdir()).name
    rel = next((ws / "projects" / "working_copies").glob("*_v2.kdenlive")).relative_to(ws)
    data = _ok(call_tool(snapshot_diff, str(ws), a=snap_id, b=str(rel)))
    assert data["a"].startswith(str(ws.resolve() / "projects" / "snapshots"))
    assert _ok(call_tool(snapshot_diff, str(ws), a="latest", b="latest"))["identical"]


@pytest.mark.parametrize("ref", ["../x.kdenlive", "..", "nope", "/etc/passwd.kdenlive"])
def test_bad_refs(ws, ref):
    result = call_tool(snapshot_diff, str(ws), a=ref)
    assert result["status"] == "error"
    assert result["error_type"] in ("not_found", "missing_file")


def test_missing_and_corrupt(ws):
    assert call_tool(snapshot_diff, str(ws), a="gone.kdenlive")["error_type"] == "missing_file"
    (ws / "bad.kdenlive").write_text("<oops")
    assert call_tool(snapshot_diff, str(ws), a="bad.kdenlive")["error_type"] == "corrupt_project"
    assert call_tool(snapshot_diff, str(ws), max_changes=0)["error_type"] == "invalid_input"
