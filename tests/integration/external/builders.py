"""Deterministic, hermetic project builders for the external oracle suite.

Projects are backed by MLT ``color:`` producers (solid colours, no media files
needed) so the acceptance tier is distro-independent. Everything here builds
plain in-memory :class:`KdenliveProject` instances that the *real* serializer
turns into ``.kdenlive`` XML.

IMPORTANT empirical note: an MLT ``color`` producer's ``resource`` must be the
bare colour value (e.g. ``0xff0000ff``). Prefixing it with ``color:`` makes MLT
render solid black, which would silently defeat the pixel-differential tests.

Duplication note (consolidation pass 4): the colour constants, the
``color:``-producer helper, and the ``solid_color_project`` / ``sequence_project``
builders were byte-for-byte twins of ``tests/_testkit.py``. They are now
**re-exported** from the shared testkit rather than reimplemented -- the sanctioned
dependency direction is *external MAY depend on the shared testkit; the shared
testkit must NEVER depend on the external package*. ``_testkit`` is a plain,
side-effect-free helper module (no fixtures, no server import), so importing it
keeps the ``-m external`` partition clean. Only the two builders that genuinely
differ from the testkit versions live here: ``two_video_track_project`` (two
*filled* video tracks vs the testkit's v1-filled/v2-empty ``two_track_project``)
and ``build_filter_xml`` (external-render-path specific).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    ProjectProfile,
    Track,
)

# Shared, byte-identical primitives re-exported from the testkit (single source
# of truth). ``_color_producer`` keeps its historical private alias for the
# local ``two_video_track_project`` below.
from tests._testkit import (  # noqa: F401  (re-exported for external tests)
    AUDIO_TRACK,
    BLACK,
    BLUE,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    GREEN,
    RED,
    VIDEO_TRACK,
    WHITE,
    color_producer as _color_producer,
    sequence_project,
    solid_color_project,
)


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
