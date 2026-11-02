"""The load check against the real MLT bindings and the melt fallback."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_melt, requires_mlt_bindings, sequence_project, two_track_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.mlt import engine

NATIVE = Path(__file__).parents[1] / "fixtures/kdenlive_references/cross_dissolve_native.kdenlive"


def _errors(result) -> list:
    return [item for item in result.items if item.severity == "error"]


@requires_mlt_bindings
@pytest.mark.parametrize("builder", [sequence_project, two_track_project], ids=["sequence", "two_track"])
def test_our_output_matches_what_mlt_builds(tmp_path, builder):
    project = builder()
    path = tmp_path / "p.kdenlive"
    serialize_project(project, path)
    result = engine.load_check(path, project)
    assert result.engine == "bindings"
    assert _errors(result) == []


@requires_mlt_bindings
def test_a_hand_edited_out_point_is_caught(tmp_path):
    project = sequence_project()
    path = tmp_path / "p.kdenlive"
    serialize_project(project, path)
    text = path.read_text(encoding="utf-8")
    assert 'out="24"' in text
    entry_start = text.index("<entry")
    entry_end = text.index(">", entry_start)
    edited = text[:entry_start] + text[entry_start:entry_end].replace('out="24"', 'out="20"') + text[entry_end:]
    assert edited != text
    path.write_text(edited, encoding="utf-8")
    errors = _errors(engine.load_check(path, project))
    assert any("out is 24 in the model, 20 in MLT" in item.message for item in errors), errors


@requires_mlt_bindings
def test_inspect_reads_a_native_save():
    inspection = engine.run_worker("inspect", {"path": str(NATIVE)}, timeout=120)
    assert len(inspection["tracks"]) == 4
    starts = [clip["start"] for track in inspection["tracks"] for pl in track["playlists"] for clip in pl["clips"]]
    assert 197 in starts and 0 in starts


@requires_mlt_bindings
def test_ping_reports_the_version():
    found = engine.find_mlt_python()
    assert found.mlt_version


@requires_melt
def test_melt_fallback_without_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    project = sequence_project()
    path = tmp_path / "p.kdenlive"
    serialize_project(project, path)
    result = engine.load_check(path, project)
    assert result.engine == "melt"
    assert _errors(result) == []
    assert "not compare" in result.reason


@requires_mlt_bindings
def test_project_validate_reports_the_load_check(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools.timeline_project import project_validate
    from workshop_video_brain.workspace.manager import WorkspaceManager

    root = tmp_path / "ws"
    WorkspaceManager.create("Load check", tmp_path, workspace_root=root)
    working = root / "projects" / "working_copies"
    working.mkdir(parents=True, exist_ok=True)
    serialize_project(sequence_project(), working / "p_v1.kdenlive")

    result = call_tool(project_validate, str(root))
    assert result["status"] == "success", result
    assert result["data"]["load_check"]["engine"] == "bindings"
    assert not [i for i in result["data"]["issues"] if i["category"] == "load_check" and i["severity"] == "error"]

    off = call_tool(project_validate, str(root), load_check=False)
    assert "load_check" not in off["data"]
