"""Deterministic, hermetic project builders for the external oracle suite.

Projects are backed by MLT ``color:`` producers (solid colours, no media files
needed) so the acceptance tier is distro-independent. Everything here builds
plain in-memory :class:`KdenliveProject` instances that the *real* serializer
turns into ``.kdenlive`` XML.

IMPORTANT empirical note: an MLT ``color`` producer's ``resource`` must be the
bare colour value (e.g. ``0xff0000ff``). Prefixing it with ``color:`` makes MLT
render solid black, which would silently defeat the pixel-differential tests.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)

# 0xRRGGBBAA
RED = "0xff0000ff"
BLUE = "0x0000ffff"
GREEN = "0x00ff00ff"
WHITE = "0xffffffff"
BLACK = "0x000000ff"

DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 180
DEFAULT_FPS = 25.0

VIDEO_TRACK = "playlist_video"
AUDIO_TRACK = "playlist_audio"


def _color_producer(producer_id: str, resource: str, length: int) -> Producer:
    return Producer(
        id=producer_id,
        resource=resource,
        properties={
            "resource": resource,
            "mlt_service": "color",
            "length": str(length),
        },
    )


def solid_color_project(
    color: str = RED,
    frames: int = 50,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: float = DEFAULT_FPS,
    title: str = "solid",
) -> KdenliveProject:
    """One video + one audio track, a single solid-colour clip on each."""
    length = frames + 10
    prod = _color_producer("producer_0", color, length)
    p = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
    )
    p.producers = [prod]
    p.tracks = [
        Track(id=VIDEO_TRACK, track_type="video", name="Video"),
        Track(id=AUDIO_TRACK, track_type="audio", name="Audio"),
    ]
    entry = PlaylistEntry(producer_id="producer_0", in_point=0, out_point=frames - 1)
    p.playlists = [
        Playlist(id=VIDEO_TRACK, entries=[entry.model_copy(deep=True)]),
        Playlist(id=AUDIO_TRACK, entries=[entry.model_copy(deep=True)]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(frames - 1)}
    return p


def sequence_project(
    colors: list[str] | None = None,
    frames_each: int = 25,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: float = DEFAULT_FPS,
    title: str = "sequence",
) -> KdenliveProject:
    """One video (+audio) track with N back-to-back solid-colour clips.

    Each clip is a distinct producer so pixel tests can tell them apart.
    """
    colors = colors or [RED, BLUE]
    total = frames_each * len(colors)
    p = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
    )
    video_entries: list[PlaylistEntry] = []
    audio_entries: list[PlaylistEntry] = []
    for i, color in enumerate(colors):
        pid = f"producer_{i}"
        p.producers.append(_color_producer(pid, color, frames_each + 10))
        video_entries.append(
            PlaylistEntry(producer_id=pid, in_point=0, out_point=frames_each - 1)
        )
        audio_entries.append(
            PlaylistEntry(producer_id=pid, in_point=0, out_point=frames_each - 1)
        )
    p.tracks = [
        Track(id=VIDEO_TRACK, track_type="video", name="Video"),
        Track(id=AUDIO_TRACK, track_type="audio", name="Audio"),
    ]
    p.playlists = [
        Playlist(id=VIDEO_TRACK, entries=video_entries),
        Playlist(id=AUDIO_TRACK, entries=audio_entries),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(total - 1)}
    return p


def two_video_track_project(
    top_color: str = BLUE,
    bottom_color: str = RED,
    frames: int = 50,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: float = DEFAULT_FPS,
    title: str = "two_video",
) -> KdenliveProject:
    """Two video tracks (for compositions/PiP) plus an audio track.

    Track index 0 = bottom video, 1 = top video, 2 = audio (indexing into
    ``project.playlists``).
    """
    length = frames + 10
    p = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
    )
    p.producers = [
        _color_producer("producer_bottom", bottom_color, length),
        _color_producer("producer_top", top_color, length),
    ]
    p.tracks = [
        Track(id="playlist_video", track_type="video", name="V1"),
        Track(id="playlist_video2", track_type="video", name="V2"),
        Track(id=AUDIO_TRACK, track_type="audio", name="Audio"),
    ]
    p.playlists = [
        Playlist(
            id="playlist_video",
            entries=[PlaylistEntry(producer_id="producer_bottom", in_point=0, out_point=frames - 1)],
        ),
        Playlist(
            id="playlist_video2",
            entries=[PlaylistEntry(producer_id="producer_top", in_point=0, out_point=frames - 1)],
        ),
        Playlist(
            id=AUDIO_TRACK,
            entries=[PlaylistEntry(producer_id="producer_bottom", in_point=0, out_point=frames - 1)],
        ),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(frames - 1)}
    return p


def build_filter_xml(
    mlt_service: str,
    track: int,
    clip: int,
    props: list[tuple[str, str]] | None = None,
    kdenlive_id: str = "",
) -> str:
    """Build the same root-level ``<filter>`` XML the real effect tools emit.

    Mirrors ``tools._build_filter_xml`` so the effect-placement code path under
    test (``patcher.insert_effect_xml`` + serializer) is exercised faithfully.
    When the §1.1 placement fix lands, these filters move inside the clip
    ``<entry>`` and the pixel xfails flip.
    """
    root = ET.Element(
        "filter",
        {"mlt_service": mlt_service, "track": str(track), "clip_index": str(clip)},
    )
    svc = ET.SubElement(root, "property", {"name": "mlt_service"})
    svc.text = mlt_service
    if kdenlive_id:
        kid = ET.SubElement(root, "property", {"name": "kdenlive_id"})
        kid.text = kdenlive_id
    for name, value in props or []:
        prop = ET.SubElement(root, "property", {"name": name})
        prop.text = value
    return ET.tostring(root, encoding="unicode")
