"""Kdenlive project serializer.  Writes a KdenliveProject to a versioned
.kdenlive XML file under projects/working_copies/.

A snapshot of any pre-existing file at the target path is created before
writing.
"""
from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject, Track
from workshop_video_brain.workspace import snapshot as snapshot_manager

logger = logging.getLogger(__name__)

# Stable UUID namespace for deterministic producer/project UUIDs
_KDENLIVE_UUID_NS = uuid.NAMESPACE_URL

# Properties managed entirely by the serializer; skip from stored properties dict
_MANAGED_PROPS = frozenset(
    {"kdenlive:uuid", "kdenlive:id", "kdenlive:clip_type", "kdenlive:folderid"}
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
    """Deterministic UUID5 for the whole project."""
    u = uuid.uuid5(_KDENLIVE_UUID_NS, "project:" + title)
    return "{" + str(u) + "}"


def _clip_type(properties: dict[str, str]) -> str:
    """Return Kdenlive clip_type from ClipType::ProducerType enum.

    Values from kdenlive/src/definitions.h:
      0=Unknown, 1=Audio, 2=Video, 3=AV, 4=Color, 5=Image,
      6=Text, 7=SlideShow, 9=Playlist, 15=QML, 17=Timeline

    NOTE: Kdenlive 25.x writes ``kdenlive:clip_type=0`` (Unknown / auto-detect)
    on avformat ``<chain>`` elements -- the chain element itself encodes that
    it is an AV media producer, so the clip_type property is left unspecific.
    Setting it to ``3`` causes the bin loader to reject the chain.
    """
    service = properties.get("mlt_service", "")
    if service == "kdenlivetitle":
        return "6"  # Text
    if service == "color":
        return "4"  # Color
    if service in ("qimage", "pixbuf"):
        return "5"  # Image
    if service.startswith("avformat"):
        return "0"  # Auto-detect from chain (was 3 = AV; rejected by Kdenlive 25)
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Tractor IDs reserved for the v25 document shape. These are stable so that
# the parser can recognise & skip them when reconstructing the model.
_PROJECT_TRACTOR_ID = "tractor_project"
_TRACK_TRACTOR_PREFIX = "tractor_track_"


# Map (width, height, fps_num, fps_den) -> canonical Kdenlive profile name.
# Kdenlive otherwise warns "non standard framerate, will result in misplaced
# clips and frame offset" when an anonymous profile is used.
_CANONICAL_PROFILES: dict[tuple[int, int, int, int], tuple[str, str]] = {
    (1920, 1080, 30000, 1001): ("atsc_1080p_2997", "HD 1080p 29.97 fps"),
    (1920, 1080, 60000, 1001): ("atsc_1080p_5994", "HD 1080p 59.94 fps"),
    (1920, 1080, 24000, 1001): ("atsc_1080p_2398", "HD 1080p 23.98 fps"),
    (1920, 1080, 25, 1):       ("atsc_1080p_25",   "HD 1080p 25 fps"),
    (1920, 1080, 30, 1):       ("atsc_1080p_30",   "HD 1080p 30 fps"),
    (1920, 1080, 50, 1):       ("atsc_1080p_50",   "HD 1080p 50 fps"),
    (1920, 1080, 60, 1):       ("atsc_1080p_60",   "HD 1080p 60 fps"),
    (1280, 720, 30000, 1001):  ("atsc_720p_2997",  "HD 720p 29.97 fps"),
    (1280, 720, 60000, 1001):  ("atsc_720p_5994",  "HD 720p 59.94 fps"),
    (3840, 2160, 30000, 1001): ("atsc_4k_2997",    "UHD 4K 29.97 fps"),
    (3840, 2160, 60000, 1001): ("atsc_4k_5994",    "UHD 4K 59.94 fps"),
    (3840, 2160, 30, 1):       ("atsc_4k_30",      "UHD 4K 30 fps"),
}


def _canonical_profile(width: int, height: int, fps_num: int, fps_den: int) -> tuple[str, str]:
    """Return (profile_name, description) for a known (size, rate) combination.

    Falls back to an anonymous ``WxH_fpsN`` name when the combination is unknown.
    """
    key = (width, height, fps_num, fps_den)
    if key in _CANONICAL_PROFILES:
        return _CANONICAL_PROFILES[key]
    fps_round = int(round(fps_num / max(1, fps_den)))
    return (f"{width}x{height}_fps{fps_round}", f"{width}x{height} {fps_round} fps")


def _track_tractor_id(playlist_id: str) -> str:
    """Stable id for the per-track tractor wrapping a given playlist."""
    return f"{_TRACK_TRACTOR_PREFIX}{playlist_id}"


def _profile_name(profile) -> str:
    """Return a Kdenlive profile name string (anonymous form is fine)."""
    return (
        f"{profile.width}x{profile.height}"
        f"_fps{int(round(profile.fps))}"
    )


def _playlist_duration(playlist) -> int:
    """Sum of (out - in + 1) for non-blank entries; sum of (out+1) for blanks."""
    total = 0
    for entry in playlist.entries:
        if entry.producer_id:
            total += entry.out_point - entry.in_point + 1
        else:
            total += entry.out_point + 1
    return total


def _add_audio_internal_filters(parent: ET.Element, base_id: str) -> None:
    """Add the volume/panner/audiolevel filters Kdenlive expects on every audio track tractor."""
    f_volume = ET.SubElement(parent, "filter", {"id": f"{base_id}_volume"})
    _set_prop(f_volume, "window", "75")
    _set_prop(f_volume, "max_gain", "20dB")
    _set_prop(f_volume, "channel_mask", "-1")
    _set_prop(f_volume, "mlt_service", "volume")
    _set_prop(f_volume, "internal_added", "237")
    _set_prop(f_volume, "disable", "1")

    f_panner = ET.SubElement(parent, "filter", {"id": f"{base_id}_panner"})
    _set_prop(f_panner, "channel", "-1")
    _set_prop(f_panner, "mlt_service", "panner")
    _set_prop(f_panner, "internal_added", "237")
    _set_prop(f_panner, "start", "0.5")
    _set_prop(f_panner, "disable", "1")

    f_level = ET.SubElement(parent, "filter", {"id": f"{base_id}_audiolevel"})
    _set_prop(f_level, "iec_scale", "0")
    _set_prop(f_level, "mlt_service", "audiolevel")
    _set_prop(f_level, "dbpeak", "1")
    _set_prop(f_level, "disable", "1")


def serialize_project(
    project: KdenliveProject,
    output_path: Path,
) -> None:
    """Write *project* to *output_path* as a Kdenlive 25.x compatible XML file.

    The output structure mirrors what Kdenlive saves when you create a project,
    drag in a clip, and save:

    * Per-track ``<tractor>`` containers (each carries 2 sub-playlists).
    * Audio track tractors carry the standard volume / panner / audiolevel filters.
    * A UUID-id'd "main sequence" ``<tractor>`` listing every per-track tractor.
    * A final ``<tractor kdenlive:projectTractor="1">`` wrapping the sequence.

    A snapshot of any pre-existing file at the target path is taken first.
    """
    output_path = Path(output_path)
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
    # Resolve track list / tractor metadata
    # ------------------------------------------------------------------
    track_type_map: dict[str, str] = {t.id: t.track_type for t in project.tracks}
    if project.tracks:
        tracks_source = list(project.tracks)
    else:
        tracks_source = [
            Track(id=pl.id, track_type="video") for pl in project.playlists
        ]

    # ------------------------------------------------------------------
    # Compute the timeline's overall length (frames)
    # ------------------------------------------------------------------
    pl_by_id = {pl.id: pl for pl in project.playlists}
    track_durations: list[int] = []
    for track in tracks_source:
        pl = pl_by_id.get(track.id)
        track_durations.append(_playlist_duration(pl) if pl else 0)
    total_frames = max(track_durations, default=0)
    if project.tractor and "out" in project.tractor:
        try:
            override_out = int(project.tractor["out"])
            if override_out + 1 > total_frames:
                total_frames = override_out + 1
        except (TypeError, ValueError):
            pass
    if total_frames <= 0:
        total_frames = 1

    # ------------------------------------------------------------------
    # Build XML tree
    # ------------------------------------------------------------------
    root = ET.Element("mlt")
    # Keep `title` for tools/users that rely on it; Kdenlive itself ignores it.
    root.set("title", project.title)
    root.set("version", project.version)
    root.set("producer", "main_bin")
    root.set("LC_NUMERIC", "C")

    # Profile
    profile_elem = ET.SubElement(root, "profile")
    fps_num, fps_den = _fps_to_rational(project.profile.fps)
    profile_name, profile_desc = _canonical_profile(
        project.profile.width, project.profile.height, fps_num, fps_den
    )
    profile_elem.set("description", profile_desc)
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

    # ------------------------------------------------------------------
    # User producers (with kdenlive bin metadata).
    #
    # avformat-* media gets emitted *twice*: once as a timeline ``<chain>``
    # (referenced by playlist entries) and once as a bin ``<chain>`` with
    # ``kdenlive:kextractor=1`` (referenced by the main_bin entry).  Both
    # carry the same ``kdenlive:id`` and ``kdenlive:control_uuid`` so
    # Kdenlive treats them as the same source clip.  This matches how
    # Kdenlive itself saves projects; emitting a single chain produces
    # "Clip ... not found in project bin" errors on load.
    # Color, title and other generators stay as a single ``<producer>``.
    # ------------------------------------------------------------------
    bin_chain_id_for: dict[str, str] = {}

    def _emit_media_element(
        producer,
        kdenlive_id: int,
        *,
        is_bin: bool,
    ) -> ET.Element:
        service = producer.properties.get("mlt_service", "")
        is_chain = service.startswith("avformat") or service == "timewarp"
        tag = "chain" if is_chain else "producer"
        elem_id = (
            f"{producer.id}_bin" if (is_bin and is_chain) else producer.id
        )
        elem = ET.SubElement(root, tag)
        elem.set("id", elem_id)
        if "length" in producer.properties:
            try:
                length = int(producer.properties["length"])
                elem.set("out", str(max(0, length - 1)))
            except (TypeError, ValueError):
                pass
        if producer.resource:
            resource_prop = ET.SubElement(elem, "property")
            resource_prop.set("name", "resource")
            resource_prop.text = producer.resource
        for name, value in producer.properties.items():
            if name == "resource":
                continue
            if name in _MANAGED_PROPS:
                continue
            prop = ET.SubElement(elem, "property")
            prop.set("name", name)
            prop.text = value
        # Do NOT emit ``kdenlive:uuid`` on producer/chain elements -- the
        # Kdenlive bin loader (projectitemmodel.cpp ``loadBinPlaylist``) uses
        # ``property_exists("kdenlive:uuid")`` to discriminate "this is a
        # sequence", routes the entry into the sequence branch, and skips
        # registration for non-tractor producers.  Only ``kdenlive:control_uuid``
        # belongs on media chains; ``kdenlive:uuid`` belongs only on the main
        # sequence tractor.
        _set_prop(
            elem,
            "kdenlive:control_uuid",
            _producer_uuid("control:" + producer.id),
        )
        _set_prop(elem, "kdenlive:id", str(kdenlive_id))
        _set_prop(elem, "kdenlive:clip_type", _clip_type(producer.properties))
        _set_prop(
            elem,
            "kdenlive:folderid",
            producer.properties.get("kdenlive:folderid", "-1"),
        )
        if is_bin and is_chain:
            _set_prop(elem, "kdenlive:monitorPosition", "0")
            _set_prop(elem, "kdenlive:kextractor", "1")
        return elem

    for kdenlive_id, producer in enumerate(project.producers, start=2):
        service = producer.properties.get("mlt_service", "")
        is_chain = service.startswith("avformat") or service == "timewarp"
        # Timeline element (referenced by playlist <entry> children)
        _emit_media_element(producer, kdenlive_id, is_bin=False)
        # Bin element (referenced by main_bin <entry>) -- only for chains
        if is_chain:
            _emit_media_element(producer, kdenlive_id, is_bin=True)
            bin_chain_id_for[producer.id] = f"{producer.id}_bin"
        else:
            bin_chain_id_for[producer.id] = producer.id

    # ------------------------------------------------------------------
    # black_track background producer
    # ------------------------------------------------------------------
    bt_elem = ET.SubElement(root, "producer")
    bt_elem.set("id", "black_track")
    bt_elem.set("in", "0")
    bt_elem.set("out", str(total_frames - 1))
    _set_prop(bt_elem, "length", "2147483647")
    _set_prop(bt_elem, "eof", "continue")
    _set_prop(bt_elem, "resource", "black")
    _set_prop(bt_elem, "aspect_ratio", "1")
    _set_prop(bt_elem, "mlt_service", "color")
    _set_prop(bt_elem, "kdenlive:playlistid", "black_track")
    _set_prop(bt_elem, "mlt_image_format", "rgba")
    _set_prop(bt_elem, "set.test_audio", "0")

    # ------------------------------------------------------------------
    # Per-track tractors:  for each track => 2 playlists + tractor wrapping them.
    # ------------------------------------------------------------------
    for track in tracks_source:
        a_id = track.id
        b_id = f"{track.id}_kdpair"
        # Playlist A (carries the entries)
        a_elem = ET.SubElement(root, "playlist")
        a_elem.set("id", a_id)
        if track.track_type == "audio":
            _set_prop(a_elem, "kdenlive:audio_track", "1")
        playlist = pl_by_id.get(a_id)
        if playlist is not None:
            for entry in playlist.entries:
                if entry.producer_id:
                    e_elem = ET.SubElement(a_elem, "entry")
                    e_elem.set("producer", entry.producer_id)
                    e_elem.set("in", str(entry.in_point))
                    e_elem.set("out", str(entry.out_point))
                else:
                    blank = ET.SubElement(a_elem, "blank")
                    blank.set("length", str(entry.out_point + 1))

        # Playlist B (empty pair for mix transitions)
        b_elem = ET.SubElement(root, "playlist")
        b_elem.set("id", b_id)
        if track.track_type == "audio":
            _set_prop(b_elem, "kdenlive:audio_track", "1")

        # Per-track tractor wrapping the two playlists
        tt_elem = ET.SubElement(root, "tractor")
        tt_id = _track_tractor_id(track.id)
        tt_elem.set("id", tt_id)
        tt_elem.set("in", "0")
        tt_elem.set("out", str(total_frames - 1))
        if track.track_type == "audio":
            _set_prop(tt_elem, "kdenlive:audio_track", "1")
        _set_prop(tt_elem, "kdenlive:trackheight", "89")
        _set_prop(tt_elem, "kdenlive:timeline_active", "1")
        _set_prop(tt_elem, "kdenlive:collapsed", "0")
        if track.name:
            _set_prop(tt_elem, "kdenlive:track_name", track.name)
        # Sub-track refs
        sub_a = ET.SubElement(tt_elem, "track")
        sub_a.set("producer", a_id)
        sub_b = ET.SubElement(tt_elem, "track")
        sub_b.set("producer", b_id)
        if track.track_type == "audio":
            sub_a.set("hide", "video")
            sub_b.set("hide", "video")
            _add_audio_internal_filters(tt_elem, base_id=tt_id)
        else:
            sub_a.set("hide", "audio")
            sub_b.set("hide", "audio")

    # ------------------------------------------------------------------
    # Main sequence tractor (UUID id) -- the timeline Kdenlive opens.
    # ------------------------------------------------------------------
    seq_uuid = _project_uuid(project.title)
    seq_elem = ET.SubElement(root, "tractor")
    seq_elem.set("id", seq_uuid)
    seq_elem.set("in", "0")
    seq_elem.set("out", str(total_frames - 1))
    _set_prop(seq_elem, "kdenlive:uuid", seq_uuid)
    _set_prop(seq_elem, "kdenlive:clipname", "Sequence 1")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.hasAudio",
              "1" if any(t.track_type == "audio" for t in tracks_source) else "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.hasVideo",
              "1" if any(t.track_type == "video" for t in tracks_source) else "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.activeTrack", "1")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.tracksCount",
              str(len(tracks_source)))
    _set_prop(seq_elem, "kdenlive:sequenceproperties.documentuuid", seq_uuid)
    _set_prop(seq_elem, "kdenlive:sequenceproperties.audioTarget", "1")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.videoTarget", "2")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.position", "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.scrollPos", "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.tracks",
              str(len(tracks_source)))
    _set_prop(seq_elem, "kdenlive:sequenceproperties.verticalzoom", "1")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.zonein", "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.zoneout", "75")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.zoom", "8")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.disablepreview", "0")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.groups", "[\n]\n")
    _set_prop(seq_elem, "kdenlive:sequenceproperties.guides", "[\n]\n")
    _set_prop(seq_elem, "kdenlive:duration", str(total_frames))
    _set_prop(seq_elem, "kdenlive:maxduration", str(total_frames))
    _set_prop(seq_elem, "kdenlive:producer_type", "17")
    _set_prop(seq_elem, "kdenlive:id", "3")
    _set_prop(seq_elem, "kdenlive:clip_type", "0")
    _set_prop(seq_elem, "kdenlive:folderid", "2")

    # Tracks: black at index 0, then each per-track tractor
    bt_track = ET.SubElement(seq_elem, "track")
    bt_track.set("producer", "black_track")
    bt_track.set("hide", "video")
    for track in tracks_source:
        t_elem = ET.SubElement(seq_elem, "track")
        t_elem.set("producer", _track_tractor_id(track.id))

    # Per-track transitions (mix for audio, qtblend for video)
    for idx, track in enumerate(tracks_source, start=1):
        trans = ET.SubElement(seq_elem, "transition")
        trans.set("id", f"seq_trans_{idx}")
        if track.track_type == "audio":
            _set_prop(trans, "a_track", "0")
            _set_prop(trans, "b_track", str(idx))
            _set_prop(trans, "mlt_service", "mix")
            _set_prop(trans, "kdenlive_id", "mix")
            _set_prop(trans, "internal_added", "237")
            _set_prop(trans, "always_active", "1")
            _set_prop(trans, "accepts_blanks", "1")
            _set_prop(trans, "sum", "1")
        else:
            _set_prop(trans, "a_track", "0")
            _set_prop(trans, "b_track", str(idx))
            _set_prop(trans, "compositing", "0")
            _set_prop(trans, "distort", "0")
            _set_prop(trans, "rotate_center", "0")
            _set_prop(trans, "mlt_service", "qtblend")
            _set_prop(trans, "kdenlive_id", "qtblend")
            _set_prop(trans, "internal_added", "237")
            _set_prop(trans, "always_active", "1")

    # Internal volume + panner filters on the main sequence
    _add_audio_internal_filters(seq_elem, base_id="main_seq")

    # ------------------------------------------------------------------
    # main_bin playlist with full doc-properties block + bin entries
    # ------------------------------------------------------------------
    profile_name, _ = _canonical_profile(
        project.profile.width, project.profile.height, fps_num, fps_den
    )
    main_bin = ET.SubElement(root, "playlist")
    main_bin.set("id", "main_bin")
    _set_prop(main_bin, "kdenlive:folder.-1.2", "Sequences")
    _set_prop(main_bin, "kdenlive:sequenceFolder", "2")
    _set_prop(main_bin, "kdenlive:docproperties.audioChannels", "2")
    _set_prop(main_bin, "kdenlive:docproperties.binsort", "0")
    _set_prop(main_bin, "kdenlive:docproperties.documentid",
              _project_uuid("docid:" + project.title).strip("{}").replace("-", "")[:13])
    _set_prop(main_bin, "kdenlive:docproperties.enableTimelineZone", "0")
    _set_prop(main_bin, "kdenlive:docproperties.enableexternalproxy", "0")
    _set_prop(main_bin, "kdenlive:docproperties.enableproxy", "0")
    _set_prop(main_bin, "kdenlive:docproperties.generateimageproxy", "0")
    _set_prop(main_bin, "kdenlive:docproperties.generateproxy", "0")
    _set_prop(main_bin, "kdenlive:docproperties.kdenliveversion", "25.08.3")
    _set_prop(main_bin, "kdenlive:docproperties.profile", profile_name)
    _set_prop(main_bin, "kdenlive:docproperties.proxyimageminsize", "2000")
    _set_prop(main_bin, "kdenlive:docproperties.proxyimagesize", "800")
    _set_prop(main_bin, "kdenlive:docproperties.proxyminsize", "1000")
    _set_prop(main_bin, "kdenlive:docproperties.proxyresize", "640")
    _set_prop(main_bin, "kdenlive:docproperties.seekOffset", "30000")
    _set_prop(main_bin, "kdenlive:docproperties.uuid", seq_uuid)
    _set_prop(main_bin, "kdenlive:docproperties.version", "1.1")
    _set_prop(main_bin, "kdenlive:expandedFolders", "")
    _set_prop(main_bin, "kdenlive:binZoom", "4")
    _set_prop(main_bin, "kdenlive:extraBins", "project_bin:-1:0")
    _set_prop(main_bin, "kdenlive:documentnotes", "")
    _set_prop(main_bin, "kdenlive:documentnotesversion", "2")
    _set_prop(main_bin, "kdenlive:docproperties.opensequences", seq_uuid)
    _set_prop(main_bin, "kdenlive:docproperties.activetimeline", seq_uuid)
    _set_prop(main_bin, "xml_retain", "1")
    # Sequence entry must come first so Kdenlive recognises the active timeline
    seq_entry = ET.SubElement(main_bin, "entry")
    seq_entry.set("producer", seq_uuid)
    seq_entry.set("in", "0")
    seq_entry.set("out", "0")
    for producer in project.producers:
        # Kdenlive's bin validation rejects entries whose out span is zero
        # for media chains -- the bin clip ends up "not found" even when the
        # chain is registered.  Use the chain's declared length instead.
        try:
            clip_length = int(producer.properties.get("length", "0"))
        except (TypeError, ValueError):
            clip_length = 0
        bin_entry = ET.SubElement(main_bin, "entry")
        bin_entry.set("producer", bin_chain_id_for.get(producer.id, producer.id))
        bin_entry.set("in", "0")
        bin_entry.set("out", str(max(0, clip_length - 1)) if clip_length > 0 else "0")

    # ------------------------------------------------------------------
    # Final project tractor wrapper -- holds the sequence as a single track.
    # ------------------------------------------------------------------
    proj_tractor = ET.SubElement(root, "tractor")
    proj_tractor.set("id", _PROJECT_TRACTOR_ID)
    proj_tractor.set("in", "0")
    proj_tractor.set("out", str(total_frames - 1))
    _set_prop(proj_tractor, "kdenlive:projectTractor", "1")
    proj_track = ET.SubElement(proj_tractor, "track")
    proj_track.set("producer", seq_uuid)
    proj_track.set("in", "0")
    proj_track.set("out", str(total_frames - 1))

    # ------------------------------------------------------------------
    # Guides
    # ------------------------------------------------------------------
    for guide in project.guides:
        g_elem = ET.SubElement(root, "guide")
        g_elem.set("position", str(guide.position))
        g_elem.set("comment", guide.label)
        if guide.category:
            g_elem.set("type", guide.category)

    # ------------------------------------------------------------------
    # Opaque elements – re-insert verbatim (skip ones the new shape
    # already produces, otherwise we'd duplicate sequence/wrapper tractors
    # on every save).
    # ------------------------------------------------------------------
    for opaque in project.opaque_elements:
        if opaque.tag == "tractor":
            continue
        try:
            elem = ET.fromstring(opaque.xml_string)
            root.append(elem)
        except ET.ParseError as exc:
            logger.warning(
                "Could not re-insert opaque element <%s>: %s", opaque.tag, exc
            )

    # Validate well-formedness by serialising to a string first
    try:
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
        ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Serialized XML is not well-formed: {exc}") from exc

    # Write file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    with output_path.open("wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)

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
