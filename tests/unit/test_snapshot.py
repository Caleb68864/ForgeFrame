"""Unit tests for the snapshot manager."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.workspace.folders import create_workspace_structure
from workshop_video_brain.workspace.snapshot import create, list_snapshots, restore


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    create_workspace_structure(tmp_path)
    return tmp_path


@pytest.fixture()
def project_file(workspace: Path) -> Path:
    """A fake project file in projects/working_copies."""
    p = workspace / "projects" / "working_copies" / "my-project.kdenlive"
    p.write_text("<kdenlive version='1'/>", encoding="utf-8")
    return p


class TestSnapshotCreate:
    def test_creates_snapshot_directory(self, workspace, project_file):
        record = create(workspace, project_file, description="initial")
        snaps = list(( workspace / "projects" / "snapshots").iterdir())
        assert len(snaps) == 1

    def test_record_has_project_path(self, workspace, project_file):
        record = create(workspace, project_file)
        assert record.project_file_path == str(project_file)

    def test_record_has_description(self, workspace, project_file):
        record = create(workspace, project_file, description="before edit")
        assert record.description == "before edit"

    def test_original_file_unchanged(self, workspace, project_file):
        original_content = project_file.read_text()
        create(workspace, project_file)
        assert project_file.read_text() == original_content


class TestSnapshotRestore:
    def test_restore_recovers_original_content(self, workspace, project_file):
        original = project_file.read_text()
        create(workspace, project_file, description="save")
        # mutate the project file
        project_file.write_text("<kdenlive version='2'/>", encoding="utf-8")
        # find snapshot dir name
        snaps_dir = workspace / "projects" / "snapshots"
        snap_name = next(snaps_dir.iterdir()).name
        restore(workspace, snap_name)
        assert project_file.read_text() == original


class TestSnapshotList:
    def test_empty_workspace_returns_empty_list(self, workspace):
        assert list_snapshots(workspace) == []

    def test_returns_all_snapshots(self, workspace, project_file):
        create(workspace, project_file, description="first")
        create(workspace, project_file, description="second")
        records = list_snapshots(workspace)
        assert len(records) == 2

    def test_sorted_by_timestamp(self, workspace, project_file):
        create(workspace, project_file, description="a")
        create(workspace, project_file, description="b")
        records = list_snapshots(workspace)
        assert records[0].timestamp <= records[1].timestamp


class TestSnapshotProtectedPaths:
    def test_restore_refuses_media_raw(self, workspace):
        """Restore must not overwrite files in media/raw."""
        # Create a snapshot manually pointing at media/raw
        from workshop_video_brain.core.models.project import SnapshotRecord
        import uuid, yaml
        snap_dir = workspace / "projects" / "snapshots" / "fake-snap"
        snap_dir.mkdir(parents=True)
        record = SnapshotRecord(
            workspace_id=uuid.uuid4(),
            project_file_path=str(workspace / "media" / "raw" / "clip.mp4"),
            description="evil",
        )
        (snap_dir / "metadata.yaml").write_text(record.to_yaml())
        # place a dummy file
        dummy = snap_dir / "clip.mp4"
        dummy.write_text("data")
        with pytest.raises(ValueError, match="protected"):
            restore(workspace, "fake-snap")

    def test_restore_refuses_projects_source(self, workspace):
        from workshop_video_brain.core.models.project import SnapshotRecord
        import uuid
        snap_dir = workspace / "projects" / "snapshots" / "fake-snap2"
        snap_dir.mkdir(parents=True)
        record = SnapshotRecord(
            workspace_id=uuid.uuid4(),
            project_file_path=str(workspace / "projects" / "source" / "master.kdenlive"),
            description="evil",
        )
        (snap_dir / "metadata.yaml").write_text(record.to_yaml())
        (snap_dir / "master.kdenlive").write_text("<kden/>")
        with pytest.raises(ValueError, match="protected"):
            restore(workspace, "fake-snap2")
