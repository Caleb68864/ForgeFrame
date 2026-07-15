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


class SpeedRamp(TimelineIntent):
    """Keyframed speed ramp / time remap for a clip.

    Realised by the patcher as a sequence of constant-speed ``timewarp:``
    producer swaps -- one playlist entry per planned segment. ``segments`` is a
    list of ``(src_in, src_out, speed)`` triples in source-frame *offsets*
    within the clip (0 = the clip's in-point), half-open ``[src_in, src_out)``,
    as produced by ``pipelines.speed_ramp.plan_segments``.
    """
    track_ref: str = ""
    clip_index: int = 0
    segments: list[tuple[int, int, float]] = Field(default_factory=list)
    pitch_compensation: bool = False


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


class PlaceClip(TimelineIntent):
    """Place a clip at an absolute timeline frame ``T`` on a specific track.

    Unlike :class:`AddClip` (which appends at a playlist index on the first video
    track), ``PlaceClip`` positions the clip at frame ``at_frame`` on the target
    playlist and either overwrites the content there (``mode="overwrite"``) or
    splits and ripples that track right (``mode="insert"``).  The frame-exact
    placement math lives in ``pipelines.clip_place``.

    ``ripple_all_tracks`` (insert mode only) additionally shifts every *other*
    track right by the clip length at ``at_frame`` and moves guides at/after
    ``at_frame`` by the same amount, so the whole timeline stays in sync.
    """
    track_ref: str = ""
    producer_id: str = ""
    source_path: str = ""  # register a producer for this media if absent
    in_point: int = 0
    out_point: int = 0
    at_frame: int = 0
    mode: str = "overwrite"  # "overwrite" | "insert"
    ripple_all_tracks: bool = False


class MoveClipToTrack(TimelineIntent):
    """Move a real clip from one track to another (cross-track move).

    The clip at ``clip_index`` on ``from_track_ref`` is removed (leaving a blank
    of the same length, or closing the gap when ``close_gap`` is true) and placed
    on ``to_track_ref`` at ``at_frame`` (``-1`` keeps its original timeline
    start).  Placement on the target uses the same engine as :class:`PlaceClip`.
    """
    from_track_ref: str = ""
    clip_index: int = 0
    to_track_ref: str = ""
    at_frame: int = -1  # -1 = keep the clip's original timeline start
    mode: str = "overwrite"  # "overwrite" | "insert"
    close_gap: bool = False


class AddEffect(TimelineIntent):
    """Apply an MLT filter (effect) to a clip on a track.

    The patcher inserts a <filter mlt_service="{effect_name}"> element
    with <property> children for each entry in params.
    """
    track_index: int = 0
    clip_index: int = 0
    effect_name: str = ""
    params: dict[str, str] = Field(default_factory=dict)


class AddTrackFilter(TimelineIntent):
    """Attach an MLT filter to an entire track (its <playlist>), not a clip.

    Rendered by the serializer as a ``<filter>`` child of the track's
    ``<playlist>`` (after all entries) -- the only placement melt honours for a
    whole-track audio effect (verified against a live melt render; see
    ``docs/research/2026-07-03-tutorial-effect-analysis/timeline-audio-mixing.md``).

    ``track_ref`` is the playlist id; ``track_index`` an optional explicit index
    into ``project.playlists`` (used when the id cannot be resolved). ``filter_id``
    is a stable id so re-running a tool replaces rather than stacks (when
    ``replace`` is true).
    """
    track_ref: str = ""
    track_index: int = -1
    mlt_service: str = ""
    filter_id: str = ""
    properties: dict[str, str] = Field(default_factory=dict)
    replace: bool = True


class ClearTrackFilters(TimelineIntent):
    """Remove track-level filters on a track (optionally filtered).

    Used to make multi-filter tools (e.g. a multi-band EQ) idempotent: clear the
    prior band stack before adding the fresh one. ``id_prefix`` matches filter
    ids that start with the prefix; ``service`` matches ``mlt_service`` exactly.
    An empty ``id_prefix`` and ``service`` clears *all* track filters on the track.
    """
    track_ref: str = ""
    track_index: int = -1
    id_prefix: str = ""
    service: str = ""


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
