"""Workspace model."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin
from .project import VideoProject


class Workspace(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    project: VideoProject
    media_root: str
    vault_note_path: str = ""
    workspace_root: str
    config: dict = Field(default_factory=dict)
