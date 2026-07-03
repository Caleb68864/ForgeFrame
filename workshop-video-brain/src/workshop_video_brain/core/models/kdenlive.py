"""Kdenlive project internal model."""
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
    profile: ProjectProfile = Field(default_factory=ProjectProfile)
    producers: list[Producer] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)
    playlists: list[Playlist] = Field(default_factory=list)
    tractor: dict | None = None
    guides: list[Guide] = Field(default_factory=list)
    subtitles: list[SubtitleTrack] = Field(default_factory=list)
    # Document-level ``kdenlive:docproperties.*`` settings keyed by suffix
    # (e.g. ``"enableproxy"`` -> ``"1"``).  Holds non-serializer-managed doc
    # properties -- notably proxy settings -- so they round-trip on the
    # ``main_bin`` playlist.  Managed keys (version/profile/uuid/guides/
    # subtitlesList/activeSubtitleIndex) are regenerated and never stored here.
    docproperties: dict[str, str] = Field(default_factory=dict)
    opaque_elements: list[OpaqueElement] = Field(default_factory=list)
