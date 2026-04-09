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
    track_ref: str = ""  # playlist ID to target (alias for track_id)
    in_point: int = 0
    out_point: int = 0
    position: int = -1  # -1 = append at end
    source_path: str = ""  # path to media resource


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


class RemoveClip(TimelineIntent):
    """Remove a clip from a playlist by index."""
    track_ref: str = ""
    clip_index: int = 0


class MoveClip(TimelineIntent):
    """Move a clip from one position to another within the same track."""
    track_ref: str = ""
    from_index: int = 0
    to_index: int = 0


class SplitClip(TimelineIntent):
    """Split a clip at a timestamp, creating two entries."""
    track_ref: str = ""
    clip_index: int = 0
    split_at_frame: int = 0  # frame within the clip to split at


class RippleDelete(TimelineIntent):
    """Remove a clip and close the gap (shift subsequent clips left)."""
    track_ref: str = ""
    clip_index: int = 0


class SetClipSpeed(TimelineIntent):
    """Change playback speed of a clip."""
    track_ref: str = ""
    clip_index: int = 0
    speed: float = 1.0  # 0.5 = half speed, 2.0 = double speed


class AudioFade(TimelineIntent):
    """Apply audio fade in or fade out to a clip."""
    track_ref: str = ""
    clip_index: int = 0
    fade_type: str = "in"  # "in" or "out"
    duration_frames: int = 24


class SetTrackMute(TimelineIntent):
    """Mute or unmute a track."""
    track_ref: str = ""
    muted: bool = True


class SetTrackVisibility(TimelineIntent):
    """Show or hide a video track."""
    track_ref: str = ""
    visible: bool = True


class AddEffect(TimelineIntent):
    """Apply an MLT filter (effect) to a clip on a track.

    The patcher inserts a <filter mlt_service="{effect_name}"> element
    with <property> children for each entry in params.
    """
    track_index: int = 0
    clip_index: int = 0
    effect_name: str = ""
    params: dict[str, str] = Field(default_factory=dict)


class AddComposition(TimelineIntent):
    """Insert an MLT transition (composition) between two tracks.

    The patcher inserts a <transition mlt_service="{composition_type}">
    element with a_track, b_track, in, out properties and any extra params.
    """
    track_a: int = 0
    track_b: int = 0
    start_frame: int = 0
    end_frame: int = 0
    composition_type: str = ""
    params: dict[str, str] = Field(default_factory=dict)
