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

What this model does **not** name
---------------------------------
Clip effects, track filters, user transitions/compositions and track mute/hide
are **not** fields here.  Every one of them travels as an :class:`OpaqueElement`
holding verbatim XML, which the serializer places structurally on the way out.
This model names only what the serializer *regenerates* -- the document
skeleton, producers, playlist entries, guides, subtitles and doc-properties.

That is one representation, deliberately.  The model previously also declared
``EntryFilter``, ``SequenceTransition``, ``TrackMixTransition``,
``PlaylistEntry.filters`` and ``Track.muted``/``Track.hidden`` describing the
same things a second way; a serializer rewrite dropped their emission and
nothing noticed, because nothing populated them either.  Setting one had no
effect on the file written to disk.  ``tests/unit/
test_kdenlive_model_has_no_dead_declarations.py`` is what keeps that from
happening again.  The vault pages above describe *XML* contracts, which still
hold -- they are reached through the OpaqueElement route, not through a model
field.
"""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin


class ProjectProfile(SerializableMixin):
    width: int = 1920
    height: int = 1080
    fps: float = 25.0
    colorspace: str | None = None


class Link(SerializableMixin):
    """An MLT ``<link>`` inside a ``<chain>`` (e.g. the ``timeremap`` link).

    Links are the chain-era successor to filters for time-domain processing;
    the ``timeremap`` link carries an animated ``time_map``/``speed_map`` plus
    ``image_mode`` and ``pitch`` properties. ``mlt_service`` is the link service
    name; ``properties`` are its ``<property>`` children.
    """

    mlt_service: str
    properties: dict[str, str] = Field(default_factory=dict)


class Producer(SerializableMixin):
    id: str
    resource: str = ""
    properties: dict[str, str] = Field(default_factory=dict)
    # When ``links`` is non-empty the serializer emits this producer as a
    # ``<chain>`` (with the links as ``<link>`` children) instead of a plain
    # ``<producer>`` -- MLT requires links to live inside a chain. ``chain_out``
    # sets the explicit ``out`` attribute the timeremap link needs to bound its
    # remapped output length (the link reads the chain's length to size its
    # animation window). Both default to the plain-producer behaviour.
    links: list[Link] = Field(default_factory=list)
    chain_out: int | None = None


class PlaylistEntry(SerializableMixin):
    """A single entry in a playlist.  If producer_id is empty it represents a gap."""

    producer_id: str = ""
    in_point: int = 0
    out_point: int = 0
    # NOTE: clip speed is NOT a field here.  ``SetClipSpeed`` creates the
    # ``<producer mlt_service="timewarp">`` variant itself and rewrites this
    # entry's ``producer_id`` to point at it (``patcher_intents``), so the speed
    # lives in the producer the entry names.  A ``speed`` field claiming the
    # serializer emitted the timewarp producer outlived the serializer that did.
    #
    # NOTE: per-clip-use effects are NOT a field here.  A clip effect travels as
    # an ``OpaqueElement`` with ``tag="filter"`` carrying ``track=``/``clip_index=``
    # attributes; ``serializer._extract_clip_filters`` keys those by
    # ``(track, clip)`` and nests them inside the matching ``<entry>``.  That is
    # the one representation -- see ``adapters/kdenlive/effect_stack``.


class Playlist(SerializableMixin):
    id: str
    entries: list[PlaylistEntry] = Field(default_factory=list)


class Track(SerializableMixin):
    """A timeline track in the project.

    The serializer emits each Track as a per-track ``<tractor>`` wrapping
    two ``<playlist>`` children.  By default each ``<track>`` ref inside
    the per-track tractor carries a ``hide`` attribute that suppresses
    the wrong stream type (audio tracks ``hide="video"``, video tracks
    ``hide="audio"``).

    NOTE: mute / visibility is NOT a field here.  It travels as an
    ``OpaqueElement`` with ``tag="kdenlive:hide"`` carrying ``track=`` and
    ``hide=`` attributes, written by ``patcher_intents._apply_set_track_mute``
    / ``_apply_set_track_visibility`` and read by
    ``serializer._hide_directives``, which puts the value on the sequence
    tractor's ``<track>`` ref.  That is the one representation.
    """

    id: str
    track_type: str = "video"  # "video" | "audio"
    name: str | None = None


class Guide(SerializableMixin):
    position: int  # frames
    label: str = ""
    category: str | None = None
    comment: str | None = None


class SubtitleTrack(SerializableMixin):
    """A real project subtitle track.

    Attached by ``subtitles_attach`` and serialised as an
    ``avfilter.subtitles`` filter on the timeline tractor plus the
    ``subtitlesList`` / ``activeSubtitleIndex`` doc/sequence properties that
    modern Kdenlive (24/25/26) reads.  ``file`` is the path to the sidecar
    subtitle document (``.ass`` preferred, ``.srt`` accepted); ``style`` is an
    optional libass ``av.force_style`` override string (styling is normally
    baked into the ``.ass`` sidecar instead).
    """

    id: int = 0
    name: str = "Subtitle"
    file: str = ""
    style: str | None = None


class OpaqueElement(SerializableMixin):
    """An XML element that the parser did not recognise.  Stored verbatim for
    round-trip safety."""

    tag: str
    xml_string: str
    position_hint: str | None = None


class KdenliveProject(SerializableMixin):
    version: str = "7"
    title: str = ""
    # The directory this project's relative ``resource`` values resolve against
    # -- the ``<mlt root>`` attribute, or the document's own directory when that
    # attribute is absent or empty (``media_check.effective_root`` is the one
    # statement of that rule; melt resolves the same way).  The parser fills it
    # in and the serializer writes it back **verbatim**, so saving an imported
    # project to a different directory keeps its relative media pointing at the
    # same files instead of silently re-basing them.
    #
    # Empty only for a project built in memory rather than parsed: there is no
    # imported root to preserve and the serializer falls back to the output
    # file's own directory.  Setting it (or clearing it) is how a caller that
    # really is *relocating* a project retargets the resources deliberately.
    root: str = ""
    profile: ProjectProfile = Field(default_factory=ProjectProfile)
    producers: list[Producer] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    playlists: list[Playlist] = Field(default_factory=list)
    # NOTE: the timeline ``<tractor>`` is NOT a field here.  The parser used to
    # store its attributes and the serializer never read them back: every
    # tractor attribute is regenerated (the sequence tractor's ``id`` *is* the
    # sequence uuid that ``kdenlive:docproperties.uuid``/``opensequences``/
    # ``activetimeline`` reference, and ``in``/``out`` come from
    # ``serializer._content_out``), so honouring a stored value would have
    # produced an invalid document rather than a faithful one.  Across every
    # ``<tractor>`` in ``tests/fixtures`` the only attributes are ``id``, ``in``
    # and ``out``, so nothing is lost.  Tractor *children* the model does not
    # name still round-trip, as OpaqueElements with ``position_hint="tractor"``.
    guides: list[Guide] = Field(default_factory=list)
    subtitles: list[SubtitleTrack] = Field(default_factory=list)
    # Document-level ``kdenlive:docproperties.*`` settings keyed by suffix
    # (e.g. ``"enableproxy"`` -> ``"1"``).  Holds non-serializer-managed doc
    # properties -- notably proxy settings -- so they round-trip on the
    # ``main_bin`` playlist.  Managed keys (version/profile/uuid/guides/
    # subtitlesList/activeSubtitleIndex) are regenerated and never stored here.
    docproperties: dict[str, str] = Field(default_factory=dict)
    # Everything this model does not name explicitly -- every clip effect, every
    # track filter, every user composition/transition, every mute/hide directive
    # -- travels here as verbatim XML with a ``position_hint``.  The serializer
    # re-inserts it, consuming the entries it can place structurally (clip and
    # track filters into their ``<entry>``/``<playlist>``, hide directives onto
    # the sequence ``<track>`` ref) and appending the rest.
    #
    # NOTE: user transitions are NOT separate model fields.  Cross-track
    # compositions and same-track mixes are written by
    # ``patcher_intents._apply_add_composition`` / ``_apply_add_transition`` as
    # ``<transition>`` OpaqueElements and normalised on the way out by
    # ``serializer._normalize_transition_id``.  The auto-internal per-track
    # compositors (mix / frei0r.cairoblend) are regenerated from the track list
    # and are not stored at all.
    opaque_elements: list[OpaqueElement] = Field(default_factory=list)
