"""Tests for render pipeline and artifact registry (PL-05)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
    RenderArtifactRegistry,
    list_renders,
    register_render,
    run_render,
)

RENDER_MOD = "workshop_video_brain.edit_mcp.pipelines.render_pipeline"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_render_job(
    tmp_path: Path,
    status: str = "queued",
    job_id: uuid.UUID | None = None,
) -> RenderJob:
    return RenderJob(
        id=job_id or uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_path=str(tmp_path / "project.kdenlive"),
        profile="preview",
        mode="standard",
        output_path=str(tmp_path / "out.mp4"),
        status=status,
        log_path="",
        started_at=None,
        completed_at=None,
    )


# ---------------------------------------------------------------------------
# TestRenderArtifactRegistryInit
# ---------------------------------------------------------------------------


class TestRenderArtifactRegistryInit:
    def test_registry_path_inside_renders_subdir(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        assert registry._registry_path == tmp_path / "renders" / "render_registry.yaml"


# ---------------------------------------------------------------------------
# TestRegisterRender
# ---------------------------------------------------------------------------


class TestRegisterRender:
    def test_creates_yaml_file_on_first_register(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        job = make_render_job(tmp_path)
        registry.register_render(job)
        assert (tmp_path / "renders" / "render_registry.yaml").exists()

    def test_registered_job_retrievable_via_list_renders(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        job = make_render_job(tmp_path)
        registry.register_render(job)
        results = registry.list_renders()
        assert len(results) == 1
        assert str(results[0].id) == str(job.id)

    def test_registering_same_job_id_twice_replaces_entry(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        job_id = uuid.uuid4()
        job_v1 = make_render_job(tmp_path, status="queued", job_id=job_id)
        job_v2 = make_render_job(tmp_path, status="succeeded", job_id=job_id)
        registry.register_render(job_v1)
        registry.register_render(job_v2)
        results = registry.list_renders()
        assert len(results) == 1
        assert results[0].status == "succeeded"

    def test_multiple_distinct_jobs_all_stored(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        job1 = make_render_job(tmp_path)
        job2 = make_render_job(tmp_path)
        registry.register_render(job1)
        registry.register_render(job2)
        assert len(registry.list_renders()) == 2

    def test_started_at_and_completed_at_serialized_as_iso(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        # Use make_render_job (explicit status="queued" string) and add started_at
        job = make_render_job(tmp_path)
        job = job.model_copy(update={"started_at": datetime.now(tz=timezone.utc)})
        registry.register_render(job)
        # Read raw text; ISO timestamps contain "T" separator
        content = (tmp_path / "renders" / "render_registry.yaml").read_text(encoding="utf-8")
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", content)


# ---------------------------------------------------------------------------
# TestListRenders
# ---------------------------------------------------------------------------


class TestListRenders:
    def test_empty_registry_returns_empty_list(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        assert registry.list_renders() == []

    def test_corrupt_yaml_returns_empty_list(self, tmp_path):
        renders_dir = tmp_path / "renders"
        renders_dir.mkdir(parents=True)
        (renders_dir / "render_registry.yaml").write_text(
            "!!python/object:builtins.eval", encoding="utf-8"
        )
        registry = RenderArtifactRegistry(tmp_path)
        assert registry.list_renders() == []

    def test_corrupt_entry_skipped_valid_entry_returned(self, tmp_path):
        job_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        valid_entry = {
            "id": str(job_id),
            "workspace_id": str(workspace_id),
            "project_path": str(tmp_path / "project.kdenlive"),
            "profile": "preview",
            "output_path": str(tmp_path / "out.mp4"),
            "mode": "standard",
            "status": "queued",
            "log_path": "",
        }
        corrupt_entry = {"not_a_real_field": "boom"}

        renders_dir = tmp_path / "renders"
        renders_dir.mkdir(parents=True)
        (renders_dir / "render_registry.yaml").write_text(
            yaml.dump([valid_entry, corrupt_entry]), encoding="utf-8"
        )

        registry = RenderArtifactRegistry(tmp_path)
        results = registry.list_renders()
        assert len(results) == 1
        assert str(results[0].id) == str(job_id)


# ---------------------------------------------------------------------------
# TestCaptureSourceVersion
# ---------------------------------------------------------------------------


class TestCaptureSourceVersion:
    def test_captures_project_path(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        project_path = str(tmp_path / "project.kdenlive")
        result = registry._capture_source_version(project_path)
        assert result["project_path"] == project_path

    def test_captures_workspace_manifest_fields(self, tmp_path):
        ws_id = str(uuid.uuid4())
        manifest = {
            "workspace_id": ws_id,
            "project_title": "My Video",
            "status": "editing",
            "slug": "my-video",
        }
        (tmp_path / "workspace.yaml").write_text(
            yaml.dump(manifest), encoding="utf-8"
        )
        registry = RenderArtifactRegistry(tmp_path)
        result = registry._capture_source_version(str(tmp_path / "project.kdenlive"))
        assert result["workspace_id"] == ws_id
        assert result["project_title"] == "My Video"
        assert result["status"] == "editing"
        assert result["slug"] == "my-video"

    def test_missing_manifest_does_not_raise(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        result = registry._capture_source_version(str(tmp_path / "project.kdenlive"))
        assert "project_path" in result

    def test_missing_project_file_omits_mtime(self, tmp_path):
        registry = RenderArtifactRegistry(tmp_path)
        result = registry._capture_source_version(str(tmp_path / "nonexistent.kdenlive"))
        assert "mtime" not in result


# ---------------------------------------------------------------------------
# TestRegisterRenderConvenience
# ---------------------------------------------------------------------------


class TestRegisterRenderConvenience:
    def test_convenience_register_delegates_to_registry(self, tmp_path):
        job = make_render_job(tmp_path)
        register_render(tmp_path, job)
        assert (tmp_path / "renders" / "render_registry.yaml").exists()


# ---------------------------------------------------------------------------
# TestListRendersConvenience
# ---------------------------------------------------------------------------


class TestListRendersConvenience:
    def test_convenience_list_returns_same_as_registry(self, tmp_path):
        job = make_render_job(tmp_path)
        register_render(tmp_path, job)
        results = list_renders(tmp_path)
        assert len(results) == 1
        assert str(results[0].id) == str(job.id)


# ---------------------------------------------------------------------------
# TestRunRender
# ---------------------------------------------------------------------------


class TestRunRender:
    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_returns_completed_job(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_profile = MagicMock()
        mock_load_profile.return_value = mock_profile

        job = make_render_job(tmp_path)
        mock_create_job.return_value = job

        completed = make_render_job(tmp_path, status="succeeded", job_id=job.id)
        mock_execute_render.return_value = completed

        result = run_render(tmp_path, tmp_path / "project.kdenlive", "preview")
        assert result.status == "succeeded"

    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_registers_job_twice(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_load_profile.return_value = MagicMock()
        job = make_render_job(tmp_path)
        mock_create_job.return_value = job

        completed = make_render_job(tmp_path, status="succeeded", job_id=job.id)
        mock_execute_render.return_value = completed

        run_render(tmp_path, tmp_path / "project.kdenlive", "preview")

        results = list_renders(tmp_path)
        assert len(results) == 1
        assert results[0].status == "succeeded"

    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_calls_load_profile_with_correct_name(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_load_profile.return_value = MagicMock()
        job = make_render_job(tmp_path)
        mock_create_job.return_value = job
        mock_execute_render.return_value = job

        run_render(tmp_path, tmp_path / "project.kdenlive", "preview")

        mock_load_profile.assert_called_once()
        call_args = mock_load_profile.call_args
        assert call_args[0][0] == "preview" or call_args[1].get("profile_name") == "preview"

    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_calls_create_render_job_with_correct_args(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_load_profile.return_value = MagicMock()
        job = make_render_job(tmp_path)
        mock_create_job.return_value = job
        mock_execute_render.return_value = job

        project_path = tmp_path / "project.kdenlive"
        run_render(tmp_path, project_path, "preview")

        mock_create_job.assert_called_once()
        kwargs = mock_create_job.call_args[1]
        assert "workspace_root" in kwargs or mock_create_job.call_args[0]

    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_calls_execute_render(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_load_profile.return_value = MagicMock()
        job = make_render_job(tmp_path)
        mock_create_job.return_value = job
        mock_execute_render.return_value = job

        run_render(tmp_path, tmp_path / "project.kdenlive", "preview")

        mock_execute_render.assert_called_once()

    @patch(f"{RENDER_MOD}.execute_render")
    @patch(f"{RENDER_MOD}.create_render_job")
    @patch(f"{RENDER_MOD}.load_profile")
    def test_run_render_propagates_executor_exception(
        self, mock_load_profile, mock_create_job, mock_execute_render, tmp_path
    ):
        mock_load_profile.return_value = MagicMock()
        job = make_render_job(tmp_path)
        mock_create_job.return_value = job
        mock_execute_render.side_effect = RuntimeError("executor failed")

        with pytest.raises(RuntimeError, match="executor failed"):
            run_render(tmp_path, tmp_path / "project.kdenlive", "preview")
