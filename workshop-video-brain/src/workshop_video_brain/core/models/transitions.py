"""Transition models for timeline editing."""
from __future__ import annotations

from enum import Enum

from pydantic import Field

from ._base import SerializableMixin


class TransitionType(str, Enum):
    """Supported transition types."""
    crossfade = "crossfade"
    dissolve = "dissolve"
    fade_in = "fade_in"
    fade_out = "fade_out"
    audio_crossfade = "audio_crossfade"


class TransitionPreset(str, Enum):
    """Standard duration presets in frames (at 25fps base).

    short  = 12 frames (~0.5s at 25fps)
    medium = 24 frames (~1s at 25fps)
    long   = 48 frames (~2s at 25fps)
    """
    short = "short"
    medium = "medium"
    long = "long"

    @property
    def frames(self) -> int:
        """Return the frame count for this preset."""
        return _PRESET_FRAMES[self]


_PRESET_FRAMES: dict[TransitionPreset, int] = {
    TransitionPreset.short: 12,
    TransitionPreset.medium: 24,
    TransitionPreset.long: 48,
}


class TransitionInstruction(SerializableMixin):
    """A fully specified transition ready to apply to a Kdenlive project."""

    model_config = {"use_enum_values": True}

    type: TransitionType = TransitionType.crossfade
    track_ref: str = ""
    left_clip_ref: str = ""
    right_clip_ref: str = ""
    duration_frames: int = 0
    audio_link_behavior: str = "linked"  # "linked" | "independent" | "mute"
    reason: str = ""
