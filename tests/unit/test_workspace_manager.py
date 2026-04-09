"""Unit tests for WorkspaceManager."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.enums import ProjectStatus
from workshop_video_brain.workspace.folders import WORKSPACE_FOLDERS
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest


class TestWorkspaceManagerCreate:
    def test_creates_workspace_yaml(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "my-project"
        WorkspaceManager.create(
            title="My Project",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        assert (ws_root / "workspace.yaml").exists()

    def test_folder_structure_created(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "test-project"
        WorkspaceManager.create(
            title="Test Project",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        for folder in WORKSPACE_FOLDERS:
            assert (ws_root / folder).is_dir(), f"Missing folder: {folder}"

    def test_returns_workspace_with_correct_title(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws = WorkspaceManager.create(
            title="Cool Video",
            media_root=str(media),
            workspace_root=str(tmp_path / "cool-video"),
        )
        assert ws.project.title == "Cool Video"

    def test_returns_workspace_with_correct_slug(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws = WorkspaceManager.create(
            title="My Awesome Video",
            media_root=str(media),
            workspace_root=str(tmp_path / "my-awesome-video"),
        )
        assert ws.project.slug == "my-awesome-video"

    def test_manifest_project_title_matches(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "titled"
        WorkspaceManager.create(
            title="Titled Project",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        manifest = read_manifest(ws_root)
        assert manifest.project_title == "Titled Project"

    def test_manifest_slug_matches(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "slug-test"
        WorkspaceManager.create(
            title="Slug Test",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        manifest = read_manifest(ws_root)
        assert manifest.slug == "slug-test"

    def test_default_workspace_root_is_sibling_of_media(self, tmp_path: Path):
        media = tmp_path / "video-clips"
        media.mkdir()
        ws = WorkspaceManager.create(
            title="Auto Root",
            media_root=str(media),
        )
        # workspace_root should be at tmp_path / "auto-root"
        assert Path(ws.workspace_root).parent == tmp_path

    def test_initial_status_is_idea(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws = WorkspaceManager.create(
            title="Status Test",
            media_root=str(media),
            workspace_root=str(tmp_path / "status-test"),
        )
        assert ws.project.status == ProjectStatus.idea.value

    def test_config_stored_in_workspace(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws = WorkspaceManager.create(
            title="Config Test",
            media_root=str(media),
            workspace_root=str(tmp_path / "config-test"),
            config={"vault_path": "/vault"},
        )
        assert ws.config.get("vault_path") == "/vault"


class TestWorkspaceManagerOpen:
    def _create_ws(self, tmp_path: Path, title: str = "Open Test") -> Path:
        media = tmp_path / "media"
        media.mkdir(exist_ok=True)
        ws_root = tmp_path / "workspace"
        WorkspaceManager.create(
            title=title,
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        return ws_root

    def test_open_reads_existing_workspace(self, tmp_path: Path):
        ws_root = self._create_ws(tmp_path, "Existing Project")
        ws = WorkspaceManager.open(ws_root)
        assert ws.project.title == "Existing Project"

    def test_open_sets_workspace_root(self, tmp_path: Path):
        ws_root = self._create_ws(tmp_path)
        ws = WorkspaceManager.open(ws_root)
        assert Path(ws.workspace_root) == ws_root

    def test_open_fails_gracefully_on_missing_manifest(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            WorkspaceManager.open(empty_dir)


class TestUpdateStatus:
    def test_update_status_changes_project_status(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "update-test"
        ws = WorkspaceManager.create(
            title="Update Test",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        WorkspaceManager.update_status(ws, ProjectStatus.editing)
        assert ws.project.status == ProjectStatus.editing.value

    def test_update_status_persists_to_manifest(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "persist-test"
        ws = WorkspaceManager.create(
            title="Persist Test",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        WorkspaceManager.update_status(ws, ProjectStatus.review)
        # Read manifest back from disk to confirm
        manifest = read_manifest(ws_root)
        assert manifest.status == ProjectStatus.review.value

    def test_update_status_accepts_string_value(self, tmp_path: Path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "str-status"
        ws = WorkspaceManager.create(
            title="String Status",
            media_root=str(media),
            workspace_root=str(ws_root),
        )
        WorkspaceManager.update_status(ws, "scripting")
        assert ws.project.status == "scripting"
