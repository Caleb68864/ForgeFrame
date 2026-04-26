"""Producer-construction helpers for the Kdenlive serializer.

Kdenlive 25.x rejects ``<producer>`` / ``<chain>`` elements that don't
carry the right properties:

* ``mlt_service`` -- without it the bin loader can't decide what kind
  of producer to instantiate.
* ``length`` -- without it the clip's duration is undefined and the
  bin entry shows zero seconds.
* ``seekable``, ``eof``, ``audio_index``/``video_index``,
  ``vstream``/``astream``, ``mute_on_pause`` -- all observed on every
  avformat producer in the KDE test suite.

Multiple call sites in this codebase build avformat producers from
scratch: the ``AddClip`` patcher path (``_apply_add_clip``), and the
build-from-data pipelines (``selects_timeline``, ``review_timeline``,
``assembly``).  They all need the same property set, so the
construction lives here as a single helper.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.kdenlive import Producer


def normalize_resource_path(path: str | Path) -> str:
    """Return *path* as a forward-slash string suitable for emit.

    Kdenlive's bin loader on Windows accepts forward slashes universally
    but treats backslashes inconsistently (sometimes drops the bin clip
    on round-trip).  Always forward-slashed in the project file.
    """
    if not path:
        return ""
    return str(path).replace("\\", "/")


def make_avformat_producer(
    producer_id: str,
    resource_path: str | Path,
    *,
    length_frames: int,
    audio_index: int = 1,
    video_index: int = 0,
    vstream: int = 0,
    astream: int = 0,
) -> Producer:
    """Construct a ``Producer`` for an avformat media file with all the
    v25-required properties already populated.

    The serializer turns this into a ``<chain mlt_service="avformat-novalidate">``
    element with its bin twin (``mlt_service="avformat"``,
    ``kdenlive:kextractor=1``, ``kdenlive:monitorPosition=0``).  Kdenlive
    25.x will load the clip into the bin with the correct duration and
    play it without the "Clip ... not found in project bin" error.

    Args:
        producer_id: The element id.  Anything that doesn't collide with
            reserved names (``main_bin``, ``black_track``,
            ``tractor_project``, ``tractor_track_*``).
        resource_path: Absolute path to the media file.  Will be
            forward-slashed regardless of OS.
        length_frames: Total clip length in frames at the project's fps.
            Must be >= 1.  The serializer derives the producer's ``out``
            attribute from this (``length - 1``).
        audio_index, video_index, vstream, astream: Stream indices the
            clip uses.  Defaults match a typical single-stream-each H.264
            + AAC mp4.  Override only when the source has a non-standard
            stream layout.
    """
    normalized = normalize_resource_path(resource_path)
    properties: dict[str, str] = {}
    if normalized:
        properties["resource"] = normalized
        properties["mlt_service"] = "avformat-novalidate"
        properties["length"] = str(max(1, length_frames))
        properties["eof"] = "pause"
        properties["seekable"] = "1"
        properties["audio_index"] = str(audio_index)
        properties["video_index"] = str(video_index)
        properties["vstream"] = str(vstream)
        properties["astream"] = str(astream)
        properties["mute_on_pause"] = "0"
        try:
            size = Path(normalized).stat().st_size
            if size:
                properties["kdenlive:file_size"] = str(size)
        except OSError:
            pass
    return Producer(
        id=producer_id,
        resource=normalized,
        properties=properties,
    )
