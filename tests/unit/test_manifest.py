"""Unit tests for workspace manifest model and read/write helpers."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml

from workshop_video_brain.core.models.enums import ProjectStatus
from workshop_video_brain.workspace.manifest import (
    WorkspaceManifest,
    read_manifest,
    write_manifest,
)


class TestWorkspaceManifestModel:
    def test_default_status_is_idea(self):
        m = WorkspaceManifest(project_title="My Project")
        assert m.status == ProjectStatus.idea.value

    def test_workspace_id_auto_generated(self):
        m = WorkspaceManifest(project_title="Test")
        assert isinstance(m.workspace_id, UUID)

    def test_custom_fields_stored(self):
        uid = uuid4()
        m = WorkspaceManifest(
            workspace_id=uid,
            project_title="Workshop",
            slug="workshop",
            status=ProjectStatus.editing,
            media_root="/media/raw",
        )
        assert m.workspace_id == uid
        assert m.project_title == "Workshop"
        assert m.slug == "workshop"
        assert m.media_root == "/media/raw"

    def test_serialise_to_yaml(self):
        m = WorkspaceManifest(project_title="Serialize Me", slug="serialize-me")
        raw = m.to_yaml()
        data = yaml.safe_load(raw)
        assert data["project_title"] == "Serialize Me"
        assert data["slug"] == "serialize-me"

    def test_deserialise_from_yaml(self):
        uid = uuid4()
        raw = yaml.dump(
            {
                "workspace_id": str(uid),
                "project_title": "Round Trip",
                "slug": "round-trip",
                "status": "editing",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "media_root": "/some/path",
            }
        )
        m = WorkspaceManifest.from_yaml(raw)
        assert m.workspace_id == uid
        assert m.project_title == "Round Trip"
        assert m.status == "editing"


class TestReadWriteManifest:
    def test_write_creates_workspace_yaml(self, tmp_path: Path):
        m = WorkspaceManifest(project_title="Write Test", slug="write-test")
        write_manifest(tmp_path, m)
        assert (tmp_path / "workspace.yaml").exists()

    def test_written_file_is_valid_yaml(self, tmp_path: Path):
        m = WorkspaceManifest(project_title="YAML Check", slug="yaml-check")
        write_manifest(tmp_path, m)
        raw = (tmp_path / "workspace.yaml").read_text()
        data = yaml.safe_load(raw)
        assert isinstance(data, dict)

    def test_read_returns_manifest(self, tmp_path: Path):
        uid = uuid4()
        m = WorkspaceManifest(
            workspace_id=uid,
            project_title="Read Me",
            slug="read-me",
            media_root="/data/video",
        )
        write_manifest(tmp_path, m)
        loaded = read_manifest(tmp_path)
        assert loaded.workspace_id == uid
        assert loaded.project_title == "Read Me"
        assert loaded.slug == "read-me"
        assert loaded.media_root == "/data/video"

    def test_read_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_manifest(tmp_path)

    def test_round_trip_preserves_all_fields(self, tmp_path: Path):
        uid = uuid4()
        original = WorkspaceManifest(
            workspace_id=uid,
            project_title="Round Trip",
            slug="round-trip",
            status=ProjectStatus.scripting,
            media_root="/media/project",
            vault_note_path="Notes/project.md",
            stt_engine="faster-whisper",
        )
        write_manifest(tmp_path, original)
        loaded = read_manifest(tmp_path)

        assert loaded.workspace_id == original.workspace_id
        assert loaded.project_title == original.project_title
        assert loaded.slug == original.slug
        assert loaded.status == original.status
        assert loaded.media_root == original.media_root
        assert loaded.vault_note_path == original.vault_note_path
        assert loaded.stt_engine == original.stt_engine
