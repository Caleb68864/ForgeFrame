"""Render pipeline and artifact registry.

Tracks render jobs in the workspace, recording source project version,
profile used, and final artifact location.
"""
from __future__ import annotations

import logging
import hashlib
from pathlib import Path
from typing import Callable

import yaml

from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.workspace.safe_write import atomic_write_text, locked_path
from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.edit_mcp.adapters.render.jobs import update_job_status
from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
from workshop_video_brain.edit_mcp.adapters.render.jobs import (
    create_render_job,
)
from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    load_profile,
)

logger = logging.getLogger(__name__)

_REGISTRY_FILENAME = "render_registry.yaml"
_RENDERS_DIR = "renders"


class RenderArtifactRegistry:
    """Tracks render jobs and their artifacts for a workspace.

    The registry is persisted as ``renders/render_registry.yaml`` inside
    the workspace root.  Each entry records the job ID, profile, output path,
    status, timestamps, and a snapshot of the source project version.
    """

    def __init__(self, workspace_root: Path | str) -> None:
        self._root = Path(workspace_root)
        self._registry_path = self._root / _RENDERS_DIR / _REGISTRY_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_render(self, job: RenderJob) -> None:
        """Add or update a render job in the registry.

        Captures the current workspace manifest as the source project version.

        Args:
            job: RenderJob to register.
        """
        with locked_path(self._registry_path):
            entries = self._load_entries()
            entry = self._job_to_entry(job)
            previous = next((existing for existing in entries if existing.get("id") == entry["id"]), None)
            if previous and previous.get("source_version"):
                entry["source_version"] = previous["source_version"]
            # Replace existing entry for this job ID if present
            entries = [e for e in entries if e.get("id") != entry["id"]]
            entries.append(entry)
            self._save_entries(entries)
        logger.info("Registered render job %s (status=%s)", job.id, job.status)

    def list_renders(self, workspace_root: Path | str | None = None) -> list[RenderJob]:
        """Return all registered render jobs for this workspace.

        Args:
            workspace_root: Ignored — present for API consistency.

        Returns:
            List of RenderJob objects, sorted by creation time.
        """
        entries = self._load_entries()
        jobs: list[RenderJob] = []
        for entry in entries:
            try:
                jobs.append(RenderJob(**entry))
            except Exception as exc:
                logger.warning("Skipping corrupt registry entry: %s", exc)
        return jobs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_entries(self) -> list[dict]:
        if not self._registry_path.exists():
            return []
        try:
            raw = yaml.safe_load(self._registry_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list) or any(not isinstance(entry, dict) for entry in raw):
                raise ValueError("Render registry must be a list of job records")
            return raw
        except Exception as exc:
            raise ValueError(f"Cannot read render registry {self._registry_path}: {exc}") from exc

    def _save_entries(self, entries: list[dict]) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self._registry_path,
            yaml.dump(entries, default_flow_style=False, allow_unicode=True),
            workspace_root=self._root,
        )

    def _job_to_entry(self, job: RenderJob) -> dict:
        """Serialize a RenderJob to a registry entry dict."""
        entry = {
            "id": str(job.id),
            "workspace_id": str(job.workspace_id),
            "project_path": job.project_path,
            "profile": job.profile,
            "output_path": job.output_path,
            "mode": job.mode,
            "status": job.status if isinstance(job.status, str) else job.status.value,
            "log_path": job.log_path,
            "duration_seconds": job.duration_seconds,
            "file_size_bytes": job.file_size_bytes,
            "source_version": self._capture_source_version(job.project_path),
        }
        if job.started_at:
            entry["started_at"] = job.started_at.isoformat()
        if job.completed_at:
            entry["completed_at"] = job.completed_at.isoformat()
        # Only written when a failure had something to say, so entries for
        # successful renders keep their existing shape.
        if job.error_message:
            entry["error_message"] = job.error_message
        if job.error_type:
            entry["error_type"] = job.error_type
        return entry

    def _capture_source_version(self, project_path: str) -> dict:
        """Capture metadata about the source project at the time of render."""
        info: dict = {"project_path": project_path}

        # Record manifest state if available
        manifest_path = self._root / "workspace.yaml"
        if manifest_path.exists():
            try:
                manifest_data = yaml.safe_load(
                    manifest_path.read_text(encoding="utf-8")
                ) or {}
                info["workspace_id"] = manifest_data.get("workspace_id", "")
                info["project_title"] = manifest_data.get("project_title", "")
                info["status"] = manifest_data.get("status", "")
                info["slug"] = manifest_data.get("slug", "")
            except Exception:
                pass

        # Record source file modification time
        p = Path(project_path)
        if p.exists():
            import os
            info["mtime"] = os.path.getmtime(str(p))
            info["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()

        return info


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def register_render(workspace_root: Path | str, job: RenderJob) -> None:
    """Register a render job in the workspace artifact registry.

    Convenience wrapper around RenderArtifactRegistry.register_render.
    """
    registry = RenderArtifactRegistry(workspace_root)
    registry.register_render(job)


def list_renders(workspace_root: Path | str) -> list[RenderJob]:
    """Return all registered render jobs for the workspace.

    Convenience wrapper around RenderArtifactRegistry.list_renders.
    """
    registry = RenderArtifactRegistry(workspace_root)
    return registry.list_renders()


def run_render(
    workspace_root: Path | str,
    project_path: Path | str,
    profile_name: str,
    mode: str = "standard",
    profiles_dir: Path | str | None = None,
    *,
    loaded_profile: RenderProfile | None = None,
    output_path: Path | str | None = None,
    timeout_seconds: int = 1800,
    on_job: Callable[[RenderJob], None] | None = None,
) -> RenderJob:
    """Create, execute, and register a render job end-to-end.

    Args:
        workspace_root: Workspace root directory.
        project_path: Path to the project file to render.
        profile_name: Render profile name, e.g. "preview".
        mode: Render mode, e.g. "standard", "proxy".
        profiles_dir: Optional override for profile YAML directory.

    Returns:
        Completed RenderJob with final status.
    """
    workspace_root = Path(workspace_root)
    project_path = Path(project_path)

    # Load profile
    profile: RenderProfile = loaded_profile or load_profile(profile_name, profiles_dir)

    # Create job
    job = create_render_job(
        workspace_root=workspace_root,
        project_path=project_path,
        profile=profile_name,
        mode=mode,
    )

    # The already loaded profile is authoritative, including custom directories.
    generated_path = Path(job.output_path).with_suffix("." + profile.output_extension)
    job = job.model_copy(update={"output_path": str(generated_path), "log_path": f"{generated_path}.log"})

    if output_path is not None:
        job = job.model_copy(update={"output_path": str(output_path), "log_path": f"{output_path}.log"})

    # Register as queued
    register_render(workspace_root, job)
    if on_job is not None:
        on_job(job)

    # Proxy render safety: a full-res render must never silently use a proxy.
    # Kdenlive stores the PROXY path in each producer's ``resource`` at edit time
    # (verified against KDE source), so melt would render low-res.  For every mode
    # except the explicit "proxy" preview, render a resources-swapped copy whose
    # producers point back at their originals (Kdenlive's KdenliveDoc::useOriginals).
    render_source = project_path
    if mode != "proxy" and project_path.suffix.lower() == ".kdenlive":
        try:
            from workshop_video_brain.edit_mcp.pipelines.proxy_wiring import (
                originals_render_copy,
            )
            render_source = originals_render_copy(
                project_path, workspace_root / "renders" / ".proxy_originals"
            )
        except Exception as exc:  # pragma: no cover - defensive
            failed = update_job_status(job, JobStatus.failed).model_copy(
                update={"error_message": f"Cannot prepare original media for render: {exc}", "error_type": "missing_file"}
            )
            register_render(workspace_root, failed)
            return failed

    exec_job = (
        job
        if Path(render_source) == project_path
        else job.model_copy(
            update={"project_path": str(Path(render_source).resolve())}
        )
    )

    # Execute
    register_render(workspace_root, update_job_status(job, JobStatus.running))
    try:
        completed_job = execute_render(exec_job, profile, timeout_seconds=timeout_seconds)
    except Exception as exc:
        completed_job = update_job_status(job, JobStatus.failed).model_copy(
            update={"error_message": f"Render execution failed: {exc}", "error_type": "operation_failed"},
        )
    # Keep the registry pointing at the original project, not the swap copy.
    if exec_job is not job:
        completed_job = completed_job.model_copy(
            update={"project_path": job.project_path}
        )

    # Register final status
    register_render(workspace_root, completed_job)

    return completed_job
