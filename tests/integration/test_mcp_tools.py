"""Integration tests for MCP tool functions.

Tests exercise the tool functions directly (not via MCP transport), calling
them with real temp workspaces and verifying structured dict output.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

# Skip the entire module if fastmcp is unavailable (e.g. system Python without venv)
fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

# Ensure tools module is loaded (registers @mcp.tool decorators)
import workshop_video_brain.edit_mcp.server.tools as _tools  # noqa: F401

from workshop_video_brain.edit_mcp.server.tools import (
    workspace_create,
    workspace_status,
    markers_auto_generate,
    project_validate,
    snapshot_list,
    media_list_assets,
    render_status,
    project_create_working_copy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path: Path, title: str = "Test Project") -> dict:
    """Create a workspace and return the workspace_create result dict."""
    media_root = str(tmp_path / "media_source")
    Path(media_root).mkdir(parents=True, exist_ok=True)
    result = workspace_create(title=title, media_root=media_root)
    assert result["status"] == "success", f"workspace_create failed: {result}"
    return result


def _fake_transcript(transcripts_dir: Path, stem: str = "clip") -> None:
    """Write a minimal fake transcript JSON for marker generation tests."""
    from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
    from uuid import uuid4
    t = Transcript(
        asset_id=uuid4(),
        engine="test",
        model="test",
        language="en",
        segments=[
            TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="Hello and welcome to this tutorial."),
            TranscriptSegment(start_seconds=5.0, end_seconds=15.0, text="Today we are going to demonstrate a step."),
            TranscriptSegment(start_seconds=15.0, end_seconds=30.0, text="First make sure you have all materials."),
            TranscriptSegment(start_seconds=30.0, end_seconds=60.0, text="Let me explain how this works step by step."),
        ],
        raw_text="Hello and welcome to this tutorial. Today we demonstrate a step.",
    )
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    (transcripts_dir / f"{stem}_transcript.json").write_text(t.to_json(), encoding="utf-8")


# ---------------------------------------------------------------------------
# workspace_create
# ---------------------------------------------------------------------------


class TestWorkspaceCreate:
    def test_returns_success_dict(self, tmp_path):
        result = workspace_create(
            title="My Video",
            media_root=str(tmp_path / "media"),
        )
        assert result["status"] == "success"

    def test_data_contains_workspace_root(self, tmp_path):
        result = workspace_create(
            title="My Video",
            media_root=str(tmp_path / "media"),
        )
        assert "workspace_root" in result["data"]

    def test_data_contains_workspace_id(self, tmp_path):
        result = workspace_create(
            title="My Video",
            media_root=str(tmp_path / "media"),
        )
        assert "workspace_id" in result["data"]

    def test_data_contains_slug(self, tmp_path):
        result = workspace_create(
            title="My Tutorial Video",
            media_root=str(tmp_path / "media"),
        )
        assert result["data"]["slug"] == "my-tutorial-video"

    def test_workspace_yaml_created_on_disk(self, tmp_path):
        result = workspace_create(
            title="Disk Check",
            media_root=str(tmp_path / "media"),
        )
        ws_root = Path(result["data"]["workspace_root"])
        assert (ws_root / "workspace.yaml").exists()

    def test_error_on_invalid_nested_path(self, tmp_path):
        # workspace_create should succeed regardless; test resilience
        result = workspace_create(
            title="Nested",
            media_root=str(tmp_path / "deep" / "nested" / "media"),
        )
        # Should succeed; WorkspaceManager does not require media_root to exist
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# workspace_status
# ---------------------------------------------------------------------------


class TestWorkspaceStatus:
    def test_returns_success_for_valid_workspace(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert result["status"] == "success"

    def test_data_contains_title(self, tmp_path):
        created = workspace_create(title="Status Test", media_root=str(tmp_path / "m"))
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert result["data"]["project_title"] == "Status Test"

    def test_error_on_missing_workspace(self, tmp_path):
        result = workspace_status(workspace_path=str(tmp_path / "nonexistent"))
        assert result["status"] == "error"
        assert "message" in result

    def test_data_has_status_field(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert "status" in result["data"]


# ---------------------------------------------------------------------------
# markers_auto_generate
# ---------------------------------------------------------------------------


class TestMarkersAutoGenerate:
    def test_returns_success_with_no_transcripts(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = markers_auto_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["marker_files"] == 0

    def test_generates_markers_from_transcript(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "sample")
        result = markers_auto_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["marker_files"] >= 1
        assert result["data"]["total_markers"] >= 1

    def test_writes_marker_json_to_disk(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        marker_files = list((Path(ws_root) / "markers").glob("*_markers.json"))
        assert len(marker_files) >= 1

    def test_marker_json_is_valid_list(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        for mf in (Path(ws_root) / "markers").glob("*_markers.json"):
            data = json.loads(mf.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert all("category" in m for m in data)

    def test_idempotent_second_run(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        r1 = markers_auto_generate(workspace_path=ws_root)
        r2 = markers_auto_generate(workspace_path=ws_root)
        assert r1["data"]["total_markers"] == r2["data"]["total_markers"]


# ---------------------------------------------------------------------------
# project_validate
# ---------------------------------------------------------------------------


class TestProjectValidate:
    def test_error_when_no_kdenlive_files(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = project_validate(workspace_path=ws_root)
        assert result["status"] == "error"

    def test_validates_generated_working_copy(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Create a working copy first
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "summary" in result["data"]
        assert "issues" in result["data"]

    def test_valid_project_has_zero_blocking_errors(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        blocking = [
            i for i in result["data"]["issues"]
            if i["severity"] == "blocking_error"
        ]
        assert len(blocking) == 0

    def test_returns_project_file_path(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        assert "project_file" in result["data"]
        assert result["data"]["project_file"].endswith(".kdenlive")


# ---------------------------------------------------------------------------
# snapshot_list
# ---------------------------------------------------------------------------


class TestSnapshotList:
    def test_returns_success_with_empty_snapshots(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = snapshot_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_returns_snapshot_after_create(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Create a working copy and snapshot it
        copy_result = project_create_working_copy(workspace_path=ws_root)
        assert copy_result["status"] == "success"
        kdenlive_path = Path(copy_result["data"]["kdenlive_path"])
        from workshop_video_brain.workspace.snapshot import create as create_snapshot
        create_snapshot(ws_root, kdenlive_path, description="test snapshot")
        result = snapshot_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] >= 1

    def test_snapshot_list_has_expected_fields(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        copy_result = project_create_working_copy(workspace_path=ws_root)
        kdenlive_path = Path(copy_result["data"]["kdenlive_path"])
        from workshop_video_brain.workspace.snapshot import create as create_snapshot
        create_snapshot(ws_root, kdenlive_path, description="field check")
        result = snapshot_list(workspace_path=ws_root)
        assert len(result["data"]["snapshots"]) >= 1
        snap = result["data"]["snapshots"][0]
        assert "id" in snap
        assert "timestamp" in snap
        assert "description" in snap


# ---------------------------------------------------------------------------
# Additional: media_list_assets and render_status
# ---------------------------------------------------------------------------


class TestMediaListAssets:
    def test_empty_result_when_no_raw_dir(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = media_list_assets(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0


class TestRenderStatus:
    def test_empty_jobs_when_no_renders(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = render_status(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
