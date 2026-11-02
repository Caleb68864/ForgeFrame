"""effect_add refuses a service it cannot use, before anything is written."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests._testkit import call_tool
from workshop_video_brain.edit_mcp.adapters.mlt.registry import ServiceRegistry, use_registry
from workshop_video_brain.edit_mcp.server.tools.effects_catalog import effect_add
from workshop_video_brain.workspace.manager import WorkspaceManager

FIXTURE = Path(__file__).parents[1] / "integration/fixtures/keyframe_project.kdenlive"
FAKE = ServiceRegistry("melt", "7.42.0", {
    "filters": frozenset({"avfilter.gblur", "avfilter.boxblur"}),
    "transitions": frozenset(),
    "producers": frozenset(),
    "consumers": frozenset(),
    "links": frozenset(),
})


@pytest.fixture
def workspace(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Effects", tmp_path, workspace_root=root)
    shutil.copy(FIXTURE, root / "test.kdenlive")
    return root


def _snapshots(root: Path) -> list[Path]:
    return sorted((root / "projects").rglob("*snapshot*"))


def test_unknown_service_writes_nothing(workspace):
    project = workspace / "test.kdenlive"
    before, snapshots = project.read_bytes(), _snapshots(workspace)
    with use_registry(FAKE):
        result = call_tool(effect_add, str(workspace), "test.kdenlive", 2, 0, "avfilter.gblurr")
    assert result["error_type"] == "invalid_input"
    assert "avfilter.gblur" in result["suggestion"]
    assert result["suggestions"][0] == "avfilter.gblur"
    assert project.read_bytes() == before
    assert _snapshots(workspace) == snapshots


def test_allow_unregistered_succeeds_and_says_so(workspace):
    with use_registry(FAKE):
        result = call_tool(effect_add, str(workspace), "test.kdenlive", 2, 0, "custom.plugin", allow_unregistered=True)
    assert result["status"] == "success", result
    assert result["data"]["service_check"] == "skipped"


def test_known_service_reports_ok(workspace):
    with use_registry(FAKE):
        result = call_tool(effect_add, str(workspace), "test.kdenlive", 2, 0, "avfilter.gblur")
    assert result["status"] == "success", result
    assert result["data"]["service_check"] == "ok"


@pytest.mark.parametrize("allow", [False, True])
def test_denylisted_service_gets_its_substitute(workspace, allow):
    with use_registry(FAKE):
        result = call_tool(effect_add, str(workspace), "test.kdenlive", 2, 0, "avfilter.boxblur", allow_unregistered=allow)
    assert result["error_type"] == "invalid_input"
    assert result["substitute"] == "box_blur"
    assert "box_blur" in result["suggestion"]
