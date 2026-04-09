---
scenario_id: "WS-01"
title: "Workspace Manager"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario WS-01: Workspace Manager

## Description
Tests the `WorkspaceManager` static-method API in `workspace/manager.py`.

The three core operations are:

| Method | What it does |
|--------|-------------|
| `create` | Builds folder structure, writes `workspace.yaml`, returns `Workspace` |
| `open` | Reads `workspace.yaml` from an existing path, returns `Workspace` |
| `save_manifest` | Re-serialises the in-memory `Workspace` back to `workspace.yaml` |

Additional coverage: `update_status` updates project status in memory and
flushes the manifest.

Edge cases: `open` on a missing path raises, `create` with an explicit
`workspace_root` overrides the default slug-derived path.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- `tmp_path` provides isolated workspace directories.
- No external processes required.

## Test Cases

```python
# tests/unit/test_workspace_manager.py
from pathlib import Path
from uuid import UUID

import pytest

from workshop_video_brain.core.models.enums import ProjectStatus
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest
from workshop_video_brain.workspace.folders import WORKSPACE_FOLDERS


class TestWorkspaceManagerCreate:
    def test_returns_workspace_with_correct_title(self, tmp_path: Path):
        ws = WorkspaceManager.create("Bandsaw Box", media_root=tmp_path / "media")
        assert ws.project.title == "Bandsaw Box"

    def test_slug_derived_from_title(self, tmp_path: Path):
        ws = WorkspaceManager.create("Bandsaw Box", media_root=tmp_path / "media")
        assert ws.project.slug == "bandsaw-box"

    def test_initial_status_is_idea(self, tmp_path: Path):
        ws = WorkspaceManager.create("Bandsaw Box", media_root=tmp_path / "media")
        assert ws.project.status == ProjectStatus.idea

    def test_workspace_root_has_standard_folders(self, tmp_path: Path):
        ws_root = tmp_path / "bandsaw-box"
        WorkspaceManager.create(
            "Bandsaw Box",
            media_root=tmp_path / "media",
            workspace_root=ws_root,
        )
        for folder in WORKSPACE_FOLDERS:
            assert (ws_root / folder).is_dir(), f"Missing: {folder}"

    def test_manifest_file_written(self, tmp_path: Path):
        ws_root = tmp_path / "bandsaw-box"
        WorkspaceManager.create(
            "Bandsaw Box",
            media_root=tmp_path / "media",
            workspace_root=ws_root,
        )
        assert (ws_root / "workspace.yaml").exists()

    def test_manifest_title_matches(self, tmp_path: Path):
        ws_root = tmp_path / "bandsaw-box"
        WorkspaceManager.create(
            "Bandsaw Box",
            media_root=tmp_path / "media",
            workspace_root=ws_root,
        )
        manifest = read_manifest(ws_root)
        assert manifest.project_title == "Bandsaw Box"

    def test_workspace_id_is_uuid(self, tmp_path: Path):
        ws = WorkspaceManager.create("Bandsaw Box", media_root=tmp_path / "media")
        assert isinstance(ws.id, UUID)

    def test_explicit_workspace_root_used(self, tmp_path: Path):
        explicit_root = tmp_path / "custom-root"
        ws = WorkspaceManager.create(
            "Bandsaw Box",
            media_root=tmp_path / "media",
            workspace_root=explicit_root,
        )
        assert ws.workspace_root == str(explicit_root)
        assert explicit_root.is_dir()

    def test_config_stored_on_workspace(self, tmp_path: Path):
        cfg = {"fps": 30, "proxy_scale": "1/2"}
        ws = WorkspaceManager.create(
            "Test",
            media_root=tmp_path / "media",
            config=cfg,
        )
        assert ws.config == cfg

    def test_empty_config_defaults_to_empty_dict(self, tmp_path: Path):
        ws = WorkspaceManager.create("Test", media_root=tmp_path / "media")
        assert ws.config == {}


class TestWorkspaceManagerOpen:
    def _create_workspace(self, tmp_path: Path, title: str = "My Project") -> Path:
        ws_root = tmp_path / "my-project"
        WorkspaceManager.create(title, media_root=tmp_path / "media", workspace_root=ws_root)
        return ws_root

    def test_open_returns_workspace(self, tmp_path: Path):
        ws_root = self._create_workspace(tmp_path)
        ws = WorkspaceManager.open(ws_root)
        assert ws is not None

    def test_open_restores_title(self, tmp_path: Path):
        ws_root = self._create_workspace(tmp_path, "My Project")
        ws = WorkspaceManager.open(ws_root)
        assert ws.project.title == "My Project"

    def test_open_restores_workspace_id(self, tmp_path: Path):
        ws_root = self._create_workspace(tmp_path)
        original = WorkspaceManager.open(ws_root)
        reopened = WorkspaceManager.open(ws_root)
        assert original.id == reopened.id

    def test_open_missing_path_raises(self, tmp_path: Path):
        with pytest.raises(Exception):
            WorkspaceManager.open(tmp_path / "does-not-exist")

    def test_open_restores_media_root(self, tmp_path: Path):
        media = tmp_path / "media"
        ws_root = tmp_path / "proj"
        WorkspaceManager.create("P", media_root=media, workspace_root=ws_root)
        ws = WorkspaceManager.open(ws_root)
        assert ws.media_root == str(media)


class TestWorkspaceManagerSaveManifest:
    def test_save_manifest_writes_updated_title(self, tmp_path: Path):
        ws_root = tmp_path / "proj"
        ws = WorkspaceManager.create("Original", media_root=tmp_path / "media", workspace_root=ws_root)
        ws.project.title = "Updated"
        WorkspaceManager.save_manifest(ws)
        manifest = read_manifest(ws_root)
        assert manifest.project_title == "Updated"

    def test_save_then_open_roundtrip(self, tmp_path: Path):
        ws_root = tmp_path / "proj"
        ws = WorkspaceManager.create("RoundTrip", media_root=tmp_path / "m", workspace_root=ws_root)
        ws.project.status = ProjectStatus.editing
        WorkspaceManager.save_manifest(ws)
        reopened = WorkspaceManager.open(ws_root)
        assert reopened.project.status == ProjectStatus.editing


class TestWorkspaceManagerUpdateStatus:
    def test_update_status_changes_project_status(self, tmp_path: Path):
        ws_root = tmp_path / "proj"
        ws = WorkspaceManager.create("S", media_root=tmp_path / "m", workspace_root=ws_root)
        WorkspaceManager.update_status(ws, ProjectStatus.scripting)
        assert ws.project.status == ProjectStatus.scripting

    def test_update_status_persists_to_disk(self, tmp_path: Path):
        ws_root = tmp_path / "proj"
        ws = WorkspaceManager.create("S", media_root=tmp_path / "m", workspace_root=ws_root)
        WorkspaceManager.update_status(ws, ProjectStatus.filming)
        manifest = read_manifest(ws_root)
        assert manifest.status == ProjectStatus.filming
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/workspace/manager.py`
2. Create `tests/unit/test_workspace_manager.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_workspace_manager.py -v`

## Expected Results
- `WorkspaceManager.create` produces the full folder tree, writes `workspace.yaml`, and returns a `Workspace` with correct fields.
- `WorkspaceManager.open` restores the workspace from disk with matching ID and title.
- `WorkspaceManager.open` on a missing path raises an exception.
- `WorkspaceManager.save_manifest` writes changes back to `workspace.yaml`.
- `update_status` updates both in-memory state and the on-disk manifest.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
