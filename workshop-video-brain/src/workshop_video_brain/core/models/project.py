"""Project-level models: VideoProject, RenderJob, SnapshotRecord."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin
from .enums import JobStatus, ProjectStatus


class VideoProject(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    title: str
    slug: str = ""
    status: ProjectStatus = ProjectStatus.idea
    content_type: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RenderJob(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    project_path: str
    profile: str = ""
    output_path: str = ""
    mode: str = ""
    status: JobStatus = JobStatus.queued
    started_at: datetime | None = None
    completed_at: datetime | None = None
    log_path: str = ""


class SnapshotRecord(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    project_file_path: str = ""
    manifest_snapshot: dict = Field(default_factory=dict)
    description: str = ""
