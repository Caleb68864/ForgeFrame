"""Workspace manifest model and read/write helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

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
    import yaml
    from workshop_video_brain.workspace.safe_write import atomic_write_text, locked_path
    path = Path(workspace_root) / _MANIFEST_FILENAME
    with locked_path(path):
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        if existing is not None and not isinstance(existing, dict):
            raise ValueError(f"Workspace manifest must be a mapping: {path}")
        def merge(current: dict, updated: dict) -> dict:
            result = dict(current)
            for key, value in updated.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
            return result

        merged = merge(existing or {}, yaml.safe_load(manifest.to_yaml()))
        atomic_write_text(path, yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
