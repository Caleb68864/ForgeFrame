"""Kdenlive project serializer.  Writes a KdenliveProject to a versioned
.kdenlive XML file under projects/working_copies/.

A snapshot of any pre-existing file at the target path is created before
writing.
"""
from __future__ import annotations

import logging
import os
import uuid
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.workspace import snapshot as snapshot_manager

logger = logging.getLogger(__name__)


class ProjectSerializeError(Exception):
    """Raised when a KdenliveProject is too inconsistent to emit a valid file.

    The serializer refuses to write a structurally-broken .kdenlive document
    (a playlist entry referencing a producer that is not defined anywhere, an
    inverted or negative clip in/out point, a non-positive blank length) rather
    than silently emitting XML that Kdenlive/melt would reject or mis-render.
    The message carries element / track / entry-index context so the caller can
    locate the offending node.  No output file is written when this is raised.
    """

# Stable UUID namespace for deterministic producer/project UUIDs
_KDENLIVE_UUID_NS = uuid.NAMESPACE_URL

# Properties managed entirely by the serializer; skip from stored properties dict.
# ``kdenlive:uuid`` and ``kdenlive:control_uuid`` are listed here so that, if a
# parsed producer carried them, they are DROPPED on re-serialize -- the modern
# (E-shape) document must not stamp media/AV bin producers with either uuid
# (only sequence tractors carry them).  ``kdenlive:id``/``clip_type``/
# ``folderid`` are regenerated fresh below.
_MANAGED_PROPS = frozenset(
    {
        "kdenlive:uuid",
        "kdenlive:control_uuid",
        "kdenlive:id",
        "kdenlive:clip_type",
        "kdenlive:folderid",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _next_version(directory: Path, stem: str) -> int:
    """Return the next version number for versioned .kdenlive files."""
    existing = list(directory.glob(f"{stem}_v*.kdenlive"))
    versions: list[int] = []
    for p in existing:
        suffix = p.stem[len(stem) + 2:]  # after "_v"
        try:
            versions.append(int(suffix))
        except ValueError:
            pass
    return max(versions, default=0) + 1


def _producer_uuid(producer_id: str) -> str:
    """Deterministic UUID5 for a producer, formatted as {uuid}."""
    u = uuid.uuid5(_KDENLIVE_UUID_NS, producer_id)
    return "{" + str(u) + "}"


def _project_uuid(title: str) -> str:
    """Deterministic UUID5 for the whole project (used as the sequence uuid)."""
    u = uuid.uuid5(_KDENLIVE_UUID_NS, "project:" + title)
    return "{" + str(u) + "}"


def _looks_like_media(resource: str) -> bool:
    """Heuristic: does *resource* point at an on-disk media file?

    A media/AV bin producer needs an ``mlt_service`` so Kdenlive's bin model
    classifies it.  Our upstream producers sometimes carry only ``resource`` +
    ``length`` (see the smoke fixtures), so the serializer defaults the service
    to ``avformat-novalidate`` when the resource is a real path.  Builtin
    producers (``black``, colour hex, ``color:``) and title/qml producers are
    excluded (they already carry their own service).
    """
    if not resource:
        return False
    if resource == "black" or resource.startswith(("#", "0x", "color:")):
        return False
    return ("/" in resource) or ("." in resource)


def _frames_to_timecode(frames: int, fps: float) -> str:
    """Format a frame count as an HH:MM:SS;FF drop-style timecode string."""
    fps_i = max(1, int(round(fps)))
    total_seconds, frame = divmod(max(0, frames), fps_i)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d};{frame:02d}"


def _clip_type(properties: dict[str, str]) -> str:
    """Return Kdenlive clip_type from ClipType::ProducerType enum.

    Values from kdenlive/src/definitions.h:
      0=Unknown, 1=Audio, 2=Video, 3=AV, 4=Color, 5=Image,
      6=Text, 7=SlideShow, 9=Playlist, 15=QML, 17=Timeline
    """
    service = properties.get("mlt_service", "")
    if service == "kdenlivetitle":
        return "6"  # Text
    if service == "color":
        return "4"  # Color
    if service in ("qimage", "pixbuf"):
        return "5"  # Image
    if service.startswith("avformat"):
        return "3"  # AV (audio+video)
    if service in ("xml", "consumer"):
        return "9"  # Playlist
    return "0"  # Unknown


def _fps_to_rational(fps: float) -> tuple[int, int]:
    """Convert fps float to (num, den) integer pair."""
    ntsc = {
        23.976: (24000, 1001),
        29.97: (30000, 1001),
        59.94: (60000, 1001),
    }
    for rate, pair in ntsc.items():
        if abs(fps - rate) < 0.01:
            return pair
    rounded = round(fps)
    if abs(fps - rounded) < 0.001:
        return rounded, 1
    return int(fps * 1000), 1000


def _display_aspect(width: int, height: int) -> tuple[int, int]:
    """Reduce width:height to display aspect ratio."""
    d = gcd(width, height)
    return width // d, height // d


def _set_prop(elem: ET.Element, name: str, value: str) -> None:
    """Append <property name="name">value</property> to *elem*."""
    prop = ET.SubElement(elem, "property")
    prop.set("name", name)
    prop.text = value


def _elem_props(elem: ET.Element) -> dict[str, ET.Element]:
    """Map ``<property name=...>`` children of *elem* by name."""
    return {
        c.get("name", ""): c
        for c in elem
        if c.tag == "property"
    }


def _normalize_transition_id(elem: ET.Element) -> None:
    """Ensure a user ``<transition>`` carries a repository ``kdenlive_id``.

    Kdenlive resolves compositing assets by ``kdenlive_id``; a composition with
    none is marked "Remove" (§FIX-2 / §(c)).  When absent, derive it from the
    transition's ``mlt_service`` (the ``frei0r.*``/``qtblend``/``mix`` services
    are already the repository dot-form id).  This is deliberately limited to
    transitions -- clip/track filters are normalised at build time by
    ``_build_filter_xml`` so render-proven ``affine`` effect paths (pan_zoom,
    zoom_whip, ...) are left untouched.
    """
    if elem.tag != "transition":
        return
    props = _elem_props(elem)
    if "kdenlive_id" in props and (props["kdenlive_id"].text or ""):
        return
    svc = elem.get("mlt_service", "")
    if "mlt_service" in props and (props["mlt_service"].text or ""):
        svc = props["mlt_service"].text or ""
    if not svc:
        return
    kid_elem = ET.Element("property")
    kid_elem.set("name", "kdenlive_id")
    kid_elem.text = svc
    insert_at = 0
    for i, child in enumerate(list(elem)):
        if child.tag == "property" and child.get("name") == "mlt_service":
            insert_at = i + 1
            break
    elem.insert(insert_at, kid_elem)


def _entry_length(entry) -> int:
    """Timeline length in frames of a playlist entry (real clip or blank)."""
    return max(0, entry.out_point - entry.in_point + 1)


def _content_out(project: KdenliveProject) -> int:
    """Return the last frame index of the longest content playlist.

    Used to bound the ``black_track`` background so a render/`-consumer null`
    stops at the actual timeline length instead of the ~2e9-frame maximum.
    """
    max_len = 0
    for playlist in project.playlists:
        total = sum(_entry_length(e) for e in playlist.entries)
        max_len = max(max_len, total)
    return max_len - 1 if max_len > 0 else 0


def _extract_clip_filters(
    project: KdenliveProject,
) -> tuple[dict[tuple[int, int], list[ET.Element]], set[int]]:
    """Pull clip filters out of ``opaque_elements`` keyed by (track, clip).

    Clip effects are stored internally as ``<filter>`` OpaqueElements carrying
    custom ``track=``/``clip_index=`` association attributes.  Real Kdenlive/MLT
    only applies filters that are *nested inside the clip ``<entry>``*, so the
    serializer relocates them there (§1.1 fix).  The association attributes are
    stripped from the emitted element (they are not MLT vocabulary); the parser
    reconstructs them on read.

    Returns ``(filters_by_clip, consumed_ids)`` where ``consumed_ids`` are the
    ``id()``s of the OpaqueElements that were relocated (so the generic opaque
    loop skips them).
    """
    by_clip: dict[tuple[int, int], list[ET.Element]] = {}
    consumed: set[int] = set()
    for opaque in project.opaque_elements:
        if opaque.tag != "filter":
            continue
        try:
            felem = ET.fromstring(opaque.xml_string)
        except ET.ParseError:
            continue
        track = felem.get("track")
        clip = felem.get("clip_index")
        if track is None or clip is None:
            continue
        try:
            key = (int(track), int(clip))
        except ValueError:
            continue
        felem.attrib.pop("track", None)
        felem.attrib.pop("clip_index", None)
        by_clip.setdefault(key, []).append(felem)
        consumed.add(id(opaque))
    return by_clip, consumed


def _extract_track_filters(
    project: KdenliveProject,
) -> tuple[dict[int, list[ET.Element]], set[int]]:
    """Pull *track-level* filters out of ``opaque_elements`` keyed by track index.

    A track filter is a ``<filter>`` OpaqueElement carrying a ``track=`` attribute
    but NO ``clip_index=`` (the absence distinguishes it from a clip effect).  MLT
    applies a filter nested in a track's ``<playlist>`` to the whole track, so the
    serializer relocates these there (§3 "Track-level audio", render-verified).
    The ``track`` association attribute is stripped from the emitted element (it
    is not MLT vocabulary); the parser reconstructs it on read.

    Returns ``(filters_by_track, consumed_ids)``.
    """
    by_track: dict[int, list[ET.Element]] = {}
    consumed: set[int] = set()
    for opaque in project.opaque_elements:
        if opaque.tag != "filter":
            continue
        try:
            felem = ET.fromstring(opaque.xml_string)
        except ET.ParseError:
            continue
        track = felem.get("track")
        if track is None or felem.get("clip_index") is not None:
            continue
        try:
            key = int(track)
        except ValueError:
            continue
        felem.attrib.pop("track", None)
        by_track.setdefault(key, []).append(felem)
        consumed.add(id(opaque))
    return by_track, consumed


def _hide_directives(
    project: KdenliveProject,
) -> tuple[dict[str, str], set[int]]:
    """Collect track hide/mute directives keyed by track id.

    Mute/visibility are represented as ``<kdenlive:hide>`` OpaqueElements
    (produced by the patcher).  The serializer applies them as the ``hide``
    attribute on the track's tractor entry -- the only place MLT honours track
    muting/visibility (§1.1 fix).  Returns ``(hide_by_track, consumed_ids)``.
    """
    hide_by_track: dict[str, str] = {}
    consumed: set[int] = set()
    for opaque in project.opaque_elements:
        if opaque.tag != "kdenlive:hide":
            continue
        try:
            helem = ET.fromstring(opaque.xml_string)
        except ET.ParseError:
            continue
        track = helem.get("track")
        if track is None:
            continue
        hide_by_track[track] = helem.get("hide", "")
        consumed.add(id(opaque))
    return hide_by_track, consumed


# ---------------------------------------------------------------------------
# Model-consistency guard
# ---------------------------------------------------------------------------


def _known_producer_ids(project: KdenliveProject) -> set[str]:
    """All producer ids that will exist in the emitted document.

    Covers the modelled producers, the always-emitted black background, and any
    ``<producer>``/``<chain>`` preserved verbatim as an OpaqueElement (real
    Kdenlive ``<chain>`` clips carry timecode ``out`` attributes the chain
    parser cannot int-cast, so they round-trip through the opaque store while
    their ids are still referenced by playlist entries -- those references are
    valid, not ghosts).
    """
    ids: set[str] = {"producer_black", "black_track"}
    for producer in project.producers:
        if producer.id:
            ids.add(producer.id)
    for opaque in project.opaque_elements:
        if opaque.tag not in ("producer", "chain"):
            continue
        try:
            el = ET.fromstring(opaque.xml_string)
        except ET.ParseError:
            continue
        pid = el.get("id")
        if pid:
            ids.add(pid)
    return ids


def _assert_serializable(project: KdenliveProject) -> None:
    """Raise :class:`ProjectSerializeError` if *project* cannot emit valid XML.

    Runs before any file I/O so a rejected project never produces a partial or
    silently-broken output document (see the class docstring for the covered
    inconsistencies).
    """
    known = _known_producer_ids(project)
    for track_index, playlist in enumerate(project.playlists):
        for i, entry in enumerate(playlist.entries):
            if entry.producer_id:
                if entry.producer_id not in known:
                    raise ProjectSerializeError(
                        f"playlist '{playlist.id}' (track {track_index}) entry #{i} "
                        f"references producer '{entry.producer_id}' which is not "
                        f"defined anywhere in the project"
                    )
                if entry.in_point < 0 or entry.out_point < 0:
                    raise ProjectSerializeError(
                        f"playlist '{playlist.id}' (track {track_index}) entry #{i} "
                        f"(producer '{entry.producer_id}') has a negative in/out "
                        f"point ({entry.in_point}/{entry.out_point})"
                    )
                if entry.out_point < entry.in_point:
                    raise ProjectSerializeError(
                        f"playlist '{playlist.id}' (track {track_index}) entry #{i} "
                        f"(producer '{entry.producer_id}') has out_point "
                        f"{entry.out_point} < in_point {entry.in_point}"
                    )
            else:
                # A gap serialises as <blank length="out_point + 1">; the length
                # must be >= 1 or the document is invalid.
                if entry.out_point < 0:
                    raise ProjectSerializeError(
                        f"playlist '{playlist.id}' (track {track_index}) blank entry "
                        f"#{i} has a non-positive length ({entry.out_point + 1})"
                    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def serialize_project(
    project: KdenliveProject,
    output_path: Path,
) -> None:
    """Write *project* to *output_path* as Kdenlive XML.

    If a file already exists at *output_path*, a snapshot is taken first.
    The file is written only after the XML is verified as well-formed.
    """
    output_path = Path(output_path)

    # Refuse structurally-inconsistent models *before* any file I/O so a bad
    # project never leaves a partial/broken document behind.
    _assert_serializable(project)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot any existing file
    if output_path.exists():
        workspace_root = output_path.parent
        for _ in range(10):
            if (workspace_root / "projects" / "working_copies").exists():
                break
            workspace_root = workspace_root.parent
        try:
            snapshot_manager.create(
                workspace_root=workspace_root,
                file_to_snapshot=output_path,
                description=f"Pre-write snapshot of {output_path.name}",
            )
        except Exception as exc:
            logger.warning("Could not create snapshot for %s: %s", output_path, exc)

    # ------------------------------------------------------------------
    # Build XML tree
    # ------------------------------------------------------------------
    root = ET.Element("mlt")
    root.set("LC_NUMERIC", "C")
    # Sub-spec 2 / E-shape: root resolves to the project (main_bin) producer and
    # carries the workspace ``root`` path so relative resources resolve.
    root.set("producer", "main_bin")
    root.set("root", str(output_path.parent))
    root.set("version", project.version)
    if project.title:
        root.set("title", project.title)

    # ------------------------------------------------------------------
    # Profile  (sub-spec 3: proper num/den + extra attributes)
    # ------------------------------------------------------------------
    profile_elem = ET.SubElement(root, "profile")
    fps_num, fps_den = _fps_to_rational(project.profile.fps)
    profile_elem.set("width", str(project.profile.width))
    profile_elem.set("height", str(project.profile.height))
    profile_elem.set("frame_rate_num", str(fps_num))
    profile_elem.set("frame_rate_den", str(fps_den))
    profile_elem.set("progressive", "1")
    profile_elem.set("sample_aspect_num", "1")
    profile_elem.set("sample_aspect_den", "1")
    dar_num, dar_den = _display_aspect(project.profile.width, project.profile.height)
    profile_elem.set("display_aspect_num", str(dar_num))
    profile_elem.set("display_aspect_den", str(dar_den))
    if project.profile.colorspace:
        profile_elem.set("colorspace", project.profile.colorspace)

    # Timeline length (last frame index) bounds the background, sequence tractor
    # and project tractor so a render/`-consumer null` stops at the content.
    content_out = _content_out(project)
    seq_uuid = _project_uuid(project.title)
    profile_name = (
        f"{project.profile.width}x{project.profile.height}"
        f"_fps{int(round(project.profile.fps))}"
    )

    # ------------------------------------------------------------------
    # Background (black) producer -- id "producer_black", carrying
    # kdenlive:playlistid=black_track (E-shape / empty_from_user ground truth).
    # ------------------------------------------------------------------
    bt_elem = ET.SubElement(root, "producer")
    bt_elem.set("id", "producer_black")
    bt_elem.set("in", "0")
    bt_elem.set("out", str(content_out))
    _set_prop(bt_elem, "length", "2147483647")
    _set_prop(bt_elem, "eof", "continue")
    _set_prop(bt_elem, "resource", "black")
    _set_prop(bt_elem, "aspect_ratio", "1")
    _set_prop(bt_elem, "mlt_service", "color")
    _set_prop(bt_elem, "kdenlive:playlistid", "black_track")
    _set_prop(bt_elem, "mlt_image_format", "rgba")
    _set_prop(bt_elem, "set.test_audio", "0")

    # ------------------------------------------------------------------
    # Media / AV bin producers (E-shape: kdenlive:id + clip_type + folderid;
    # NO kdenlive:uuid and NO kdenlive:control_uuid -- only sequence tractors
    # carry uuids, else loadBinPlaylist routes them into the sequence branch and
    # skips them as malformed sequences).
    # ------------------------------------------------------------------
    for kdenlive_id, producer in enumerate(project.producers, start=2):
        # A producer carrying MLT links serializes as a <chain> (links may only
        # live inside a chain); otherwise a plain <producer>.  The chain's `out`
        # attribute bounds the (possibly time-remapped) output length.
        if producer.links:
            p_elem = ET.SubElement(root, "chain")
            p_elem.set("id", producer.id)
            if producer.chain_out is not None:
                p_elem.set("out", str(producer.chain_out))
        else:
            p_elem = ET.SubElement(root, "producer")
            p_elem.set("id", producer.id)
        # resource property first (critical for Kdenlive to find media)
        if producer.resource:
            resource_prop = ET.SubElement(p_elem, "property")
            resource_prop.set("name", "resource")
            resource_prop.text = producer.resource
        # A media bin producer needs an mlt_service so Kdenlive classifies it.
        # Default AV producers that carry only a resource (smoke fixtures) to
        # ``avformat`` -- the *validating* demuxer, which probes the file and
        # decodes correctly.  (``avformat-novalidate`` skips probing and relies
        # on stored format metadata Kdenlive normally writes; our upstream
        # producers lack it, so novalidate renders black for lavfi-generated
        # clips.  ``avformat`` is fully GUI-loadable.)
        service = producer.properties.get("mlt_service", "")
        if not service and _looks_like_media(producer.resource):
            service = "avformat"
            _set_prop(p_elem, "mlt_service", service)
            _set_prop(p_elem, "eof", "pause")
        # Stored properties (skip resource and managed kdenlive keys)
        for name, value in producer.properties.items():
            if name == "resource":
                continue
            if name in _MANAGED_PROPS:
                continue  # dropped (uuids) or regenerated (id/clip_type/folderid)
            prop = ET.SubElement(p_elem, "property")
            prop.set("name", name)
            prop.text = value
        # Serializer-managed kdenlive metadata (regenerated; NO uuid/control_uuid)
        _set_prop(p_elem, "kdenlive:id", str(kdenlive_id))
        _set_prop(
            p_elem,
            "kdenlive:clip_type",
            _clip_type({**producer.properties, "mlt_service": service}),
        )
        _set_prop(
            p_elem,
            "kdenlive:folderid",
            producer.properties.get("kdenlive:folderid", "-1"),
        )
        # MLT <link> children (chain-only).  Each link is a service + properties.
        for link in producer.links:
            link_elem = ET.SubElement(p_elem, "link")
            link_elem.set("mlt_service", link.mlt_service)
            for name, value in link.properties.items():
                lprop = ET.SubElement(link_elem, "property")
                lprop.set("name", name)
                lprop.text = value

    # ------------------------------------------------------------------
    # Per-track lanes + track-tractors (E-shape / empty_from_user ground truth).
    # Each timeline track is a <tractor> wrapping two <playlist> lanes: the
    # clips lane (playlist.id, holds entries + nested clip/track filters) and an
    # empty companion lane (playlist.id + "_kdpair").
    # ------------------------------------------------------------------
    clip_filters, consumed_filter_ids = _extract_clip_filters(project)
    track_filters, consumed_track_filter_ids = _extract_track_filters(project)
    track_type_map: dict[str, str] = {t.id: t.track_type for t in project.tracks}
    hide_by_track, consumed_hide_ids = _hide_directives(project)

    # (track_tractor_id, track_type, clips_playlist_id, is_xfade)
    track_tractors: list[tuple[str, str, str, bool]] = []
    for track_index, playlist in enumerate(project.playlists):
        track_type = track_type_map.get(playlist.id, "video")
        lane_hide = "audio" if track_type == "video" else "video"

        # Clips lane
        pl_elem = ET.SubElement(root, "playlist")
        pl_elem.set("id", playlist.id)
        real_index = 0
        for entry in playlist.entries:
            if entry.producer_id:
                e_elem = ET.SubElement(pl_elem, "entry")
                e_elem.set("producer", entry.producer_id)
                e_elem.set("in", str(entry.in_point))
                e_elem.set("out", str(entry.out_point))
                for felem in clip_filters.get((track_index, real_index), []):
                    e_elem.append(felem)
                real_index += 1
            else:
                blank_elem = ET.SubElement(pl_elem, "blank")
                blank_elem.set("length", str(entry.out_point + 1))
        # Track-wide filters nest after all entries/blanks.
        for felem in track_filters.get(track_index, []):
            pl_elem.append(felem)

        # Empty companion lane
        b_id = f"{playlist.id}_kdpair"
        b_elem = ET.SubElement(root, "playlist")
        b_elem.set("id", b_id)

        # Track-tractor wrapping both lanes
        tt_id = f"tractor_{playlist.id}"
        tt = ET.SubElement(root, "tractor")
        tt.set("id", tt_id)
        tt.set("in", "0")
        tt.set("out", str(content_out))
        _set_prop(tt, "kdenlive:trackheight", "62")
        _set_prop(tt, "kdenlive:timeline_active", "1")
        _set_prop(tt, "kdenlive:thumbs_format", "")
        _set_prop(tt, "kdenlive:audio_rec", "")
        for lane_id in (playlist.id, b_id):
            lt = ET.SubElement(tt, "track")
            lt.set("hide", lane_hide)
            lt.set("producer", lane_id)
        # Audio tracks carry the internal volume/panner/audiolevel filters real
        # Kdenlive nests in the track-tractor (disabled no-ops; ground truth:
        # empty_from_user audio track-tractors).
        if track_type == "audio":
            for svc, extra in (
                ("volume", [("window", "75"), ("max_gain", "20dB"),
                            ("channel_mask", "-1")]),
                ("panner", [("channel", "-1"), ("start", "0.5")]),
                ("audiolevel", [("iec_scale", "0"), ("dbpeak", "1")]),
            ):
                af = ET.SubElement(tt, "filter")
                for k, v in extra:
                    _set_prop(af, k, v)
                _set_prop(af, "mlt_service", svc)
                _set_prop(af, "internal_added", "237")
                _set_prop(af, "disable", "1")

        track_tractors.append(
            (tt_id, track_type, playlist.id, "_xfade" in playlist.id)
        )

    # ------------------------------------------------------------------
    # Sequence tractor (kdenlive:producer_type=17): the registered sequence bin
    # clip.  Its element id IS the sequence uuid.  Holds the black background +
    # the track-tractors, the always-active compositing transitions, guides and
    # subtitle filters.  This is ``tractor_elem`` for opaque tractor-hinted
    # content below.
    # ------------------------------------------------------------------
    has_audio = any(tt[1] == "audio" for tt in track_tractors)
    has_video = any(tt[1] == "video" for tt in track_tractors)
    seq_kid = len(project.producers) + 2
    tractor_elem = ET.SubElement(root, "tractor")
    tractor_elem.set("id", seq_uuid)
    tractor_elem.set("in", "0")
    tractor_elem.set("out", str(content_out))
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.hasAudio",
              "1" if has_audio else "0")
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.hasVideo",
              "1" if has_video else "0")
    _set_prop(tractor_elem, "kdenlive:clip_type", "2")
    _set_prop(tractor_elem, "kdenlive:uuid", seq_uuid)
    _set_prop(tractor_elem, "kdenlive:clipname", "Sequence 1")
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.tracksCount",
              str(len(track_tractors)))
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.documentuuid", seq_uuid)
    _set_prop(tractor_elem, "kdenlive:control_uuid", seq_uuid)
    _set_prop(tractor_elem, "kdenlive:duration",
              _frames_to_timecode(content_out + 1, project.profile.fps))
    _set_prop(tractor_elem, "kdenlive:maxduration", str(content_out + 1))
    _set_prop(tractor_elem, "kdenlive:producer_type", "17")
    _set_prop(tractor_elem, "kdenlive:id", str(seq_kid))
    _set_prop(tractor_elem, "kdenlive:file_size", "0")
    _set_prop(tractor_elem, "kdenlive:folderid", "2")
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.activeTrack",
              str(len(track_tractors)) if track_tractors else "0")
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.groups", "[\n]\n")

    # Sequence tracks: black background first, then each track-tractor.
    bt_track = ET.SubElement(tractor_elem, "track")
    bt_track.set("producer", "producer_black")
    for tt_id, _ttype, clips_id, _xf in track_tractors:
        st = ET.SubElement(tractor_elem, "track")
        st.set("producer", tt_id)
        # Explicit mute/visibility directives apply on the sequence-track entry.
        if clips_id in hide_by_track and hide_by_track[clips_id]:
            st.set("hide", hide_by_track[clips_id])

    # Always-active compositing transitions (regenerated; internal_added=237).
    # Crossfade overlay tracks (_xfade) deliberately get NO always_active
    # compositor -- their compositing is driven by an explicit luma mix.
    for b_index, (_tt_id, ttype, _clips_id, is_xfade) in enumerate(
        track_tractors, start=1
    ):
        if is_xfade:
            continue
        trans_elem = ET.SubElement(tractor_elem, "transition")
        _set_prop(trans_elem, "a_track", "0")
        _set_prop(trans_elem, "b_track", str(b_index))
        if ttype == "audio":
            _set_prop(trans_elem, "mlt_service", "mix")
            _set_prop(trans_elem, "kdenlive_id", "mix")
            _set_prop(trans_elem, "internal_added", "237")
            _set_prop(trans_elem, "always_active", "1")
            _set_prop(trans_elem, "accepts_blanks", "1")
            _set_prop(trans_elem, "sum", "1")
        else:
            # frei0r.cairoblend is the melt-proven internal video compositor
            # (multi-track stacking renders correctly headless); it loads in the
            # 26.04 GUI as an internal_added track compositor.  A kdenlive_id is
            # required so Kdenlive resolves the composition asset (§FIX-2/§(c)).
            _set_prop(trans_elem, "mlt_service", "frei0r.cairoblend")
            _set_prop(trans_elem, "kdenlive_id", "frei0r.cairoblend")
            _set_prop(trans_elem, "internal_added", "237")
            _set_prop(trans_elem, "always_active", "1")

    # Guides JSON on the active sequence tractor (else an empty JSON array).
    _seq_guides = "[\n]\n"
    if project.guides:
        try:
            from workshop_video_brain.edit_mcp.pipelines.guides import (
                guides_docproperties_json,
            )
            _seq_guides = guides_docproperties_json(project)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise sequence guides JSON: %s", exc)
    _set_prop(tractor_elem, "kdenlive:sequenceproperties.guides", _seq_guides)

    # Subtitle tracks: sequenceproperties mirror + one avfilter.subtitles filter
    # per track (the only place MLT/melt render subtitle pixels).
    if project.subtitles:
        try:
            from workshop_video_brain.edit_mcp.pipelines.subtitle_track import (
                subtitles_list_json,
            )
            _set_prop(
                tractor_elem,
                "kdenlive:sequenceproperties.subtitlesList",
                subtitles_list_json(project),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise sequence subtitles JSON: %s", exc)
        for sub in project.subtitles:
            if not sub.file:
                continue
            sub_filter = ET.SubElement(tractor_elem, "filter")
            sub_filter.set("id", f"subtitle_{sub.id}")
            _set_prop(sub_filter, "mlt_service", "avfilter.subtitles")
            _set_prop(sub_filter, "av.filename", sub.file)
            _set_prop(sub_filter, "av.alpha", "1")
            if sub.style:
                _set_prop(sub_filter, "av.force_style", sub.style)
            _set_prop(sub_filter, "disable", "0")
            _set_prop(sub_filter, "internal_added", "237")
            _set_prop(sub_filter, "kdenlive:id", str(sub.id))

    # ------------------------------------------------------------------
    # main_bin playlist: bin registration.  Loaded from the project tractor's
    # xml_retain bag, so it MUST carry xml_retain=1.  Registers the media
    # producers plus the sequence clip; declares the Sequences folder and the
    # open/active timeline (= sequence uuid).
    # ------------------------------------------------------------------
    main_bin = ET.SubElement(root, "playlist")
    main_bin.set("id", "main_bin")
    _set_prop(main_bin, "kdenlive:folder.-1.2", "Sequences")
    _set_prop(main_bin, "kdenlive:sequenceFolder", "2")
    _set_prop(main_bin, "kdenlive:docproperties.version", "1.1")
    _set_prop(main_bin, "kdenlive:docproperties.profile", profile_name)
    _set_prop(main_bin, "kdenlive:docproperties.uuid", seq_uuid)
    _set_prop(main_bin, "kdenlive:docproperties.opensequences", seq_uuid)
    _set_prop(main_bin, "kdenlive:docproperties.activetimeline", seq_uuid)
    if project.guides:
        try:
            from workshop_video_brain.edit_mcp.pipelines.guides import (
                guides_docproperties_json,
            )
            _set_prop(main_bin, "kdenlive:docproperties.guides",
                      guides_docproperties_json(project))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise guides JSON: %s", exc)
    if project.subtitles:
        try:
            from workshop_video_brain.edit_mcp.pipelines.subtitle_track import (
                active_subtitle_index,
                subtitles_list_json,
            )
            _set_prop(main_bin, "kdenlive:docproperties.subtitlesList",
                      subtitles_list_json(project))
            _set_prop(main_bin, "kdenlive:docproperties.activeSubtitleIndex",
                      active_subtitle_index(project))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise subtitlesList JSON: %s", exc)
    # PROXY / doc-property bag (round-tripped, suffix-keyed).  Managed keys are
    # excluded by the parser so no duplicates arise here.
    for suffix, value in project.docproperties.items():
        _set_prop(main_bin, f"kdenlive:docproperties.{suffix}", str(value))
    _set_prop(main_bin, "xml_retain", "1")
    for producer in project.producers:
        entry = ET.SubElement(main_bin, "entry")
        entry.set("producer", producer.id)
        entry.set("in", "0")
        entry.set("out", "0")
    # Sequence clip entry (registers the sequence in the bin).
    seq_entry = ET.SubElement(main_bin, "entry")
    seq_entry.set("producer", seq_uuid)
    seq_entry.set("in", "0")
    seq_entry.set("out", "0")

    # ------------------------------------------------------------------
    # Project tractor: the MLT render root.  Carries kdenlive:projectTractor=1
    # and a single track referencing the active sequence uuid.  loadBinPlaylist
    # reads the bin from this tractor's xml_retain data.
    # ------------------------------------------------------------------
    proj_tractor = ET.SubElement(root, "tractor")
    proj_tractor.set("id", "tractor_project")
    proj_tractor.set("in", "0")
    proj_tractor.set("out", str(content_out))
    _set_prop(proj_tractor, "kdenlive:projectTractor", "1")
    pt_track = ET.SubElement(proj_tractor, "track")
    pt_track.set("producer", seq_uuid)
    pt_track.set("in", "0")
    pt_track.set("out", str(content_out))

    # ------------------------------------------------------------------
    # Guides (legacy top-level elements; harmless, kept for round-trip parse).
    # ------------------------------------------------------------------
    for guide in project.guides:
        g_elem = ET.SubElement(root, "guide")
        g_elem.set("position", str(guide.position))
        g_elem.set("comment", guide.label)
        if guide.category:
            g_elem.set("type", guide.category)

    # ------------------------------------------------------------------
    # Opaque elements -- re-insert, honouring position_hint.  Clip/track filters
    # and hide directives are already consumed; tractor-hinted content (user
    # transitions/filters) is nested back inside the sequence tractor.
    # ------------------------------------------------------------------
    consumed_ids = consumed_filter_ids | consumed_track_filter_ids | consumed_hide_ids
    for opaque in project.opaque_elements:
        if id(opaque) in consumed_ids:
            continue
        try:
            elem = ET.fromstring(opaque.xml_string)
        except ET.ParseError as exc:
            logger.warning(
                "Could not re-insert opaque element <%s>: %s", opaque.tag, exc
            )
            continue
        if elem.tag == "transition":
            _normalize_transition_id(elem)
        if opaque.position_hint == "tractor" and tractor_elem is not None:
            tractor_elem.append(elem)
        else:
            root.append(elem)

    # Validate well-formedness by serialising to a string first
    try:
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
        ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Serialized XML is not well-formed: {exc}") from exc

    # Write file atomically: serialise to a sibling temp file, then os.replace()
    # it into place.  A crash or I/O error mid-write therefore never truncates or
    # corrupts an existing project at *output_path* -- combined with the
    # well-formedness check above this guarantees the target is only ever
    # replaced by a fully-written, valid document.
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    try:
        with tmp_path.open("wb") as fh:
            fh.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
            tree.write(fh, encoding="utf-8", xml_declaration=False)
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    logger.info("Wrote Kdenlive project to %s", output_path)


def serialize_versioned(
    project: KdenliveProject,
    workspace_root: Path,
    title_slug: str,
) -> Path:
    """Serialize *project* to a versioned path inside *workspace_root*.

    Path: ``projects/working_copies/{title_slug}_v{N}.kdenlive``
    Returns the path that was written.
    """
    working_copies = workspace_root / "projects" / "working_copies"
    working_copies.mkdir(parents=True, exist_ok=True)
    version = _next_version(working_copies, title_slug)
    output_path = working_copies / f"{title_slug}_v{version}.kdenlive"
    serialize_project(project, output_path)
    return output_path
