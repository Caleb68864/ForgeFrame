"""Archive models -- manifest for workspace archive operations."""
from __future__ import annotations

from pydantic import BaseModel


class ArchiveManifest(BaseModel):
    workspace_title: str
    archive_path: str
    created_at: str  # ISO 8601
    files_included: int
    total_size_bytes: int
    includes_renders: bool
    includes_raw_media: bool
