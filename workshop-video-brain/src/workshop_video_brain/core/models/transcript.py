"""Transcript models."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin


class WordTiming(SerializableMixin):
    model_config = {"use_enum_values": True}

    word: str
    start: float
    end: float
    confidence: float = 1.0


class TranscriptSegment(SerializableMixin):
    model_config = {"use_enum_values": True}

    start_seconds: float
    end_seconds: float
    text: str
    confidence: float = 1.0
    words: list[WordTiming] = Field(default_factory=list)


class Transcript(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    asset_id: UUID
    engine: str = ""
    model: str = ""
    language: str = ""
    segments: list[TranscriptSegment] = Field(default_factory=list)
    raw_text: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
