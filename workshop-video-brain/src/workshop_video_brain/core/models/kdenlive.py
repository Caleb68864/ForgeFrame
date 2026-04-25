"""Kdenlive project internal model.

The shape this model serializes to (in ``adapters/kdenlive/serializer.py``)
follows Kdenlive 25.x / MLT 7.x conventions verified against five hand-saved
references in ``tests/fixtures/kdenlive_references/``.  Detailed contracts
for each pattern live in ``vault/wiki/kdenlive-*.md``; the most relevant:

* ``kdenlive-25-document-shape`` -- top-level structure (per-track tractors,
  main sequence, project tractor wrapper, ``main_bin`` doc-properties).
* ``kdenlive-uuid-vs-control-uuid`` -- never put ``kdenlive:uuid`` on a
  producer/chain; it makes the bin loader skip registration.
* ``kdenlive-twin-chain-pattern`` -- avformat clips emit two ``<chain>``
  elements (timeline + bin), linked by ``kdenlive:control_uuid`` and
  ``kdenlive:id``, distinguished by the ``_kdbin`` suffix on the bin twin.
* ``kdenlive-per-track-tractor-pattern`` -- each track is its own tractor
  with two playlists; audio tracks carry internal volume/panner/audiolevel
  filters.
* ``kdenlive-title-card-pattern`` -- editable titles (``mlt_service=
  kdenlivetitle`` + ``xmldata``).
* ``kdenlive-cross-dissolve-pattern`` -- stacked-clip dissolves; ``a_track <
  b_track``; encode direction via ``reverse``.
* ``kdenlive-image-and-qtblend-pattern`` -- image producers + Ken Burns
  ``qtblend`` filters with entry-local keyframes.
* ``kdenlive-clip-speed-pattern`` -- separate ``timewarp`` producer per
  unique speed; original chain stays as the bin clip.
"""
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
    Used for transform / colour / blur effects that apply to a single
    clip use -- e.g. a Ken Burns ``qtblend`` parallax pan on an image, a
    static PIP rect on a webcam overlay, an audio fade, or a colour grade.

    Important contract gotchas (see
    ``vault/wiki/kdenlive-image-and-qtblend-pattern.md`` and
    ``vault/wiki/kdenlive-audio-fade-pattern.md``):

    * Transforms use ``mlt_service=qtblend`` -- NOT ``affine``.  Kdenlive's
      UI labels both as "Transform" but writes ``qtblend``.
    * Keyframe timestamps in ``rect`` / ``rotation`` properties are
      ENTRY-LOCAL (run from ``00:00:00.000`` to the entry's local
      duration), not absolute sequence frames.
    * Audio volume fades are NOT keyframed; they use scalar ``gain`` +
      ``end`` properties and rely on the filter's ``in_frame``/``out_frame``
      attributes to define the ramp window.

    Attributes:
        id: Optional element id (Kdenlive auto-numbers these as
            ``filter6``/``filter7``/...; pass empty to omit).
        in_frame: Optional ``in=`` attribute on the ``<filter>`` element
            itself (entry-local frame index).  Used by audio fades to
            position the ramp window inside the clip.
        out_frame: Optional ``out=`` attribute on the ``<filter>`` element.
        zone_in_frame: Optional ``kdenlive:zone_in`` property -- scopes the
            effect to a sub-range of the clip (entry-local frames).  Pair
            with ``zone_out_frame`` to define the active range.  Used in
            ``effect-zones.kdenlive`` from the KDE test suite.
        zone_out_frame: Optional ``kdenlive:zone_out`` property.
        properties: All ``<property name=...>value</property>`` children,
            keyed by property name.
    """

    id: str = ""
    in_frame: int | None = None
    out_frame: int | None = None
    zone_in_frame: int | None = None
    zone_out_frame: int | None = None
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

    The serializer wires the auto-internal mix/qtblend transitions per
    track automatically; this model holds *additional* transitions like
    cross-dissolves that span an overlap region between two stacked
    clips.  See ``vault/wiki/kdenlive-cross-dissolve-pattern.md``.

    HARD RULE: ``a_track < b_track``.  The lower-numbered track ordinal
    goes into ``a_track`` regardless of dissolve direction.  Encode
    direction via the ``reverse`` property in ``properties`` (``"0"`` =
    upper fades in, ``"1"`` = upper fades out revealing lower).
    Reversing the ordinals instead produces the "Incorrect composition
    ... was set to forced track" warning at project-load.

    Attributes:
        id: Element id (e.g. ``"dissolve_v1_v2"``); must be unique.
        a_track: 1-based ordinal of the LOWER track in the main sequence's
            track list (0 = black_track).  Must be ``< b_track``.
        b_track: 1-based ordinal of the HIGHER track.
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
