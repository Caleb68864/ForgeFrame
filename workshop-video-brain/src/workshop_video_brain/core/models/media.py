"""MediaAsset model."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin
from .enums import AnalysisStatus, ProxyStatus, TranscriptStatus


class MediaAsset(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    path: str
    relative_path: str = ""
    media_type: str = ""
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    duration: float = 0.0
    duration_seconds: float = 0.0  # alias for duration (used by MCP tools)
    fps: float = 0.0
    width: int = 0
    height: int = 0
    aspect_ratio: str = ""
    channels: int = 0
    sample_rate: int = 0
    bitrate: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    file_size: int = 0
    file_size_bytes: int = 0  # alias for file_size (used by MCP tools)
    hash: str = ""
    proxy_path: str = ""
    proxy_status: ProxyStatus = ProxyStatus.not_needed
    transcript_status: TranscriptStatus = TranscriptStatus.pending
    analysis_status: AnalysisStatus = AnalysisStatus.pending
