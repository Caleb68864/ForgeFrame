"""Workspace manifest model and read/write helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import yaml
from pydantic import Field

from workshop_video_brain.core.models._base import SerializableMixin
from workshop_video_brain.core.models.enums import ProjectStatus
from workshop_video_brain.core.models.workspace import KeyframeDefaults


class WorkspaceManifest(SerializableMixin):
    model_config = {"use_enum_values": True}

    workspace_id: UUID = Field(default_factory=uuid4)
    project_title: str
    slug: str = ""
    status: ProjectStatus = ProjectStatus.idea
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    content_type: str = ""
    vault_note_path: str = ""
    media_root: str = ""
    proxy_policy: dict = Field(default_factory=dict)
    stt_engine: str = "whisper"
    default_sort_mode: str = "chronological"
    keyframe_defaults: KeyframeDefaults = Field(default_factory=KeyframeDefaults)


_MANIFEST_FILENAME = "workspace.yaml"


def read_manifest(workspace_root: Path | str) -> WorkspaceManifest:
    """Read workspace.yaml from *workspace_root* and return a WorkspaceManifest."""
    path = Path(workspace_root) / _MANIFEST_FILENAME
    raw = path.read_text(encoding="utf-8")
    return WorkspaceManifest.from_yaml(raw)


def write_manifest(workspace_root: Path | str, manifest: WorkspaceManifest) -> None:
    """Serialise *manifest* to workspace.yaml inside *workspace_root*."""
    path = Path(workspace_root) / _MANIFEST_FILENAME
    path.write_text(manifest.to_yaml(), encoding="utf-8")
