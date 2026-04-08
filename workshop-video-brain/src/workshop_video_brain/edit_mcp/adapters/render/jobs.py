"""Render job management.

Creates and updates RenderJob records. Uses the RenderJob model from core.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.workspace.manifest import read_manifest


def create_render_job(
    workspace_root: Path | str,
    project_path: Path | str,
    profile: str,
    mode: str = "standard",
) -> RenderJob:
    """Create a new RenderJob for the given workspace and project file.

    Args:
        workspace_root: Root of the workspace directory.
        project_path: Path to the Kdenlive .kdenlive project file to render.
        profile: Render profile name, e.g. "preview", "draft-youtube".
        mode: Render mode string, e.g. "standard", "proxy", "audio-only".

    Returns:
        A new RenderJob with status=queued.
    """
    workspace_root = Path(workspace_root)
    project_path = Path(project_path)

    # Try to read workspace ID from manifest
    workspace_id = uuid4()
    try:
        manifest = read_manifest(workspace_root)
        workspace_id = manifest.workspace_id
    except Exception:
        pass  # Use generated UUID if manifest is absent

    # Determine output path
    renders_dir = workspace_root / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    output_filename = f"{project_path.stem}-{profile}-{timestamp}.mp4"
    output_path = renders_dir / output_filename

    # Log file alongside output
    log_path = renders_dir / f"{output_filename}.log"

    job = RenderJob(
        workspace_id=workspace_id,
        project_path=str(project_path.resolve()),
        profile=profile,
        output_path=str(output_path),
        mode=mode,
        status=JobStatus.queued,
        log_path=str(log_path),
    )

    return job


def update_job_status(job: RenderJob, status: JobStatus | str) -> RenderJob:
    """Return a new RenderJob with updated status and timestamps.

    Does not mutate the input job.

    Args:
        job: Source RenderJob.
        status: New JobStatus value.

    Returns:
        Updated RenderJob (new instance).
    """
    if isinstance(status, str):
        status = JobStatus(status)

    updates: dict = {"status": status.value}

    if status == JobStatus.running and job.started_at is None:
        updates["started_at"] = datetime.utcnow()
    elif status in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled):
        updates["completed_at"] = datetime.utcnow()

    return job.model_copy(update=updates)
