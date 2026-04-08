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
    opaque_elements: list[OpaqueElement] = Field(default_factory=list)
