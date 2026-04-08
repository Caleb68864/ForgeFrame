"""Timeline intent models."""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin


class TimelineIntent(SerializableMixin):
    model_config = {"use_enum_values": True}


class TransitionIntent(TimelineIntent):
    type: str = ""
    track_ref: str = ""
    left_clip_ref: str = ""
    right_clip_ref: str = ""
    duration_frames: int = 0
    reason: str = ""


class SubtitleCue(TimelineIntent):
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    text: str = ""


# ---------------------------------------------------------------------------
# Expanded timeline intent models
# ---------------------------------------------------------------------------


class AddClip(TimelineIntent):
    producer_id: str = ""
    track_id: str = ""
    in_point: int = 0
    out_point: int = 0
    position: int = 0


class TrimClip(TimelineIntent):
    clip_ref: str = ""
    new_in: int = 0
    new_out: int = 0


class InsertGap(TimelineIntent):
    track_id: str = ""
    position: int = 0
    duration_frames: int = 0


class AddGuide(TimelineIntent):
    position_frames: int = 0
    label: str = ""
    category: str | None = None
    comment: str | None = None


class AddSubtitleRegion(TimelineIntent):
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    text: str = ""


class AddTransition(TimelineIntent):
    type: str = ""
    track_ref: str = ""
    left_clip_ref: str = ""
    right_clip_ref: str = ""
    duration_frames: int = 0


class CreateTrack(TimelineIntent):
    track_type: str = "video"  # "video" | "audio"
    name: str = ""
