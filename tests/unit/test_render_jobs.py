from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.jobs import (
    create_render_job,
    update_job_status,
)
from workshop_video_brain.workspace.manifest import WorkspaceManifest, write_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_manifest(workspace_root: Path, title: str = "Test Project") -> WorkspaceManifest:
    manifest = WorkspaceManifest(project_title=title, slug="test-project", media_root=str(workspace_root))
    write_manifest(workspace_root, manifest)
    return manifest


# ---------------------------------------------------------------------------
# create_render_job
# ---------------------------------------------------------------------------

class TestCreateRenderJob:
    def test_returns_render_job_instance(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert isinstance(job, RenderJob)

    def test_initial_status_is_queued(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.status == JobStatus.queued

    def test_renders_dir_created(self, tmp_path: Path):
        create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert (tmp_path / "renders").is_dir()

    def test_output_path_contains_profile_name(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "draft-youtube")
        assert "draft-youtube" in job.output_path

    def test_output_path_ends_with_mp4(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.output_path.endswith(".mp4")

    def test_log_path_is_alongside_output(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.log_path.startswith(job.output_path)  # log_path = output_path + ".log"
        assert job.log_path.endswith(".log")

    def test_workspace_id_from_manifest(self, tmp_path: Path):
        manifest = _seed_manifest(tmp_path)
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.workspace_id == manifest.workspace_id

    def test_workspace_id_generated_when_no_manifest(self, tmp_path: Path):
        # No workspace.yaml present — should not raise, just generate a UUID
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert isinstance(job.workspace_id, UUID)

    def test_project_path_is_resolved_absolute(self, tmp_path: Path):
        relative = "edit.kdenlive"
        job = create_render_job(tmp_path, tmp_path / relative, "preview")
        assert Path(job.project_path).is_absolute()

    def test_mode_stored_on_job(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview", mode="proxy")
        assert job.mode == "proxy"

    def test_default_mode_is_standard(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.mode == "standard"

    def test_profile_stored_on_job(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "final-youtube")
        assert job.profile == "final-youtube"

    def test_started_at_and_completed_at_are_none(self, tmp_path: Path):
        job = create_render_job(tmp_path, tmp_path / "edit.kdenlive", "preview")
        assert job.started_at is None
        assert job.completed_at is None


# ---------------------------------------------------------------------------
# update_job_status
# ---------------------------------------------------------------------------

class TestUpdateJobStatus:
    def _base_job(self) -> RenderJob:
        return RenderJob(
            workspace_id=uuid4(),
            project_path="/tmp/edit.kdenlive",
            profile="preview",
        )

    def test_returns_new_instance(self):
        job = self._base_job()
        updated = update_job_status(job, JobStatus.running)
        assert updated is not job

    def test_original_not_mutated(self):
        job = self._base_job()
        update_job_status(job, JobStatus.running)
        assert job.status == JobStatus.queued

    def test_status_updated_to_running(self):
        job = self._base_job()
        updated = update_job_status(job, JobStatus.running)
        assert updated.status == JobStatus.running

    def test_started_at_set_on_running(self):
        job = self._base_job()
        before = datetime.now(tz=timezone.utc)
        updated = update_job_status(job, JobStatus.running)
        assert updated.started_at is not None
        assert updated.started_at >= before

    def test_started_at_not_overwritten_on_second_running(self):
        job = self._base_job()
        first = update_job_status(job, JobStatus.running)
        original_started = first.started_at
        # If caller erroneously calls running again, started_at should not move
        second = update_job_status(first, JobStatus.running)
        assert second.started_at == original_started

    def test_completed_at_set_on_succeeded(self):
        job = self._base_job()
        updated = update_job_status(job, JobStatus.succeeded)
        assert updated.completed_at is not None

    def test_completed_at_set_on_failed(self):
        job = self._base_job()
        updated = update_job_status(job, JobStatus.failed)
        assert updated.completed_at is not None

    def test_completed_at_set_on_cancelled(self):
        job = self._base_job()
        updated = update_job_status(job, JobStatus.cancelled)
        assert updated.completed_at is not None

    def test_accepts_string_status(self):
        job = self._base_job()
        updated = update_job_status(job, "succeeded")
        assert updated.status == JobStatus.succeeded

    def test_invalid_string_status_raises(self):
        job = self._base_job()
        with pytest.raises(ValueError):
            update_job_status(job, "not_a_status")

    def test_full_lifecycle_queued_running_succeeded(self):
        job = self._base_job()
        assert job.status == JobStatus.queued
        running = update_job_status(job, JobStatus.running)
        assert running.status == JobStatus.running
        done = update_job_status(running, JobStatus.succeeded)
        assert done.status == JobStatus.succeeded
        assert done.completed_at is not None
