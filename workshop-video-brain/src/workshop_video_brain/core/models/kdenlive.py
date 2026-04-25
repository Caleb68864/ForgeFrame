"""Kdenlive project internal model."""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin


class ProjectProfile(SerializableMixin):
    width: int = 1920
    height: int = 1080
    fps: float = 25.0
    colorspace: str | None = None


class Producer(SerializableMixin):
    id: str
    resource: str = ""
    properties: dict[str, str] = Field(default_factory=dict)


class EntryFilter(SerializableMixin):
    """A filter (effect) attached to a playlist entry.

    Emitted as a ``<filter>`` child inside the entry's ``<entry>`` element.
    Used for transform/colour/blur effects that apply to a single clip use,
    such as a Ken Burns ``qtblend`` parallax pan on an image.

    Attributes:
        id: Optional element id (Kdenlive auto-numbers these as
            ``filter6``/``filter7``/...; pass empty to omit).
        properties: All ``<property name=...>value</property>`` children,
            keyed by property name.
    """

    id: str = ""
    properties: dict[str, str] = Field(default_factory=dict)


class PlaylistEntry(SerializableMixin):
    """A single entry in a playlist.  If producer_id is empty it represents a gap."""

    producer_id: str = ""
    in_point: int = 0
    out_point: int = 0
    # 1.0 = play at normal speed; other values trigger the serializer to
    # emit a separate ``<producer mlt_service="timewarp">`` for this
    # clip-use and rewrite the entry's producer reference to it.  The
    # original chain stays in place as the bin clip; only the timeline
    # entry is redirected to the timewarp variant.
    speed: float = 1.0
    # Per-clip-use effects (transforms, colour grading, blurs, etc.).  Live
    # inside the ``<entry>`` element in the emitted XML.
    filters: list[EntryFilter] = Field(default_factory=list)


class Playlist(SerializableMixin):
    id: str
    entries: list[PlaylistEntry] = Field(default_factory=list)


class Track(SerializableMixin):
    id: str
    track_type: str = "video"  # "video" | "audio"
    name: str | None = None


class Guide(SerializableMixin):
    position: int  # frames
    label: str = ""
    category: str | None = None
    comment: str | None = None


class OpaqueElement(SerializableMixin):
    """An XML element that the parser did not recognise.  Stored verbatim for
    round-trip safety."""

    tag: str
    xml_string: str
    position_hint: str | None = None


class SequenceTransition(SerializableMixin):
    """A user-added transition emitted into the main sequence tractor.

    The serializer wires the auto-internal mix/qtblend transitions per track
    automatically; this model holds *additional* transitions like cross-
    dissolves that span an overlap region between two stacked clips.

    Attributes:
        id: Element id (e.g. ``"dissolve_v1_v2"``); must be unique.
        a_track: 1-based ordinal of the lower (outgoing) track in the main
            sequence's track list (0 = black_track).
        b_track: 1-based ordinal of the upper (incoming) track.
        in_frame: Absolute sequence frame where the transition starts.
        out_frame: Absolute sequence frame where the transition ends.
        mlt_service: MLT service name, e.g. ``"luma"`` for a dissolve.
        kdenlive_id: Kdenlive's preset id, e.g. ``"dissolve"`` or ``"wipe"``.
        properties: Extra ``<property>`` children (e.g. ``softness``,
            ``reverse``, ``alpha_over``, ``fix_background_alpha``).
    """

    id: str
    a_track: int
    b_track: int
    in_frame: int
    out_frame: int
    mlt_service: str
    kdenlive_id: str
    properties: dict[str, str] = Field(default_factory=dict)


class KdenliveProject(SerializableMixin):
    version: str = "7"
    title: str = ""
    profile: ProjectProfile = Field(default_factory=ProjectProfile)
    producers: list[Producer] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    playlists: list[Playlist] = Field(default_factory=list)
    tractor: dict | None = None
    guides: list[Guide] = Field(default_factory=list)
    opaque_elements: list[OpaqueElement] = Field(default_factory=list)
    # Cross-dissolves, wipes, slides, etc. that span the overlap between two
    # stacked clips on different tracks.  Auto-internal per-track transitions
    # (mix / qtblend) are NOT stored here -- they're emitted by the
    # serializer based on the track list.  See ``SequenceTransition``.
    sequence_transitions: list[SequenceTransition] = Field(default_factory=list)
