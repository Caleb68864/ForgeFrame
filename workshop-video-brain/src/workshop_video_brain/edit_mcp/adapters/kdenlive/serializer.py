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
    """Return Kdenlive clip_type: 2 for kdenlivetitle, 0 for everything else."""
    if properties.get("mlt_service") == "kdenlivetitle":
        return "2"
    return "0"


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


def serialize_project(
    project: KdenliveProject,
    output_path: Path,
) -> None:
    """Write *project* to *output_path* as Kdenlive XML.

    If a file already exists at *output_path*, a snapshot is taken first.
    The file is written only after the XML is verified as well-formed.
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
    # Build XML tree
    # ------------------------------------------------------------------
    root = ET.Element("mlt")
    root.set("title", project.title)
    root.set("version", project.version)
    # Sub-spec 2: required root attributes
    root.set("producer", "main_bin")
    root.set("LC_NUMERIC", "C")

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

    # ------------------------------------------------------------------
    # User producers (sub-spec 1: kdenlive metadata properties)
    # ------------------------------------------------------------------
    for kdenlive_id, producer in enumerate(project.producers, start=2):
        p_elem = ET.SubElement(root, "producer")
        p_elem.set("id", producer.id)
        # resource property first (critical for Kdenlive to find media)
        if producer.resource:
            resource_prop = ET.SubElement(p_elem, "property")
            resource_prop.set("name", "resource")
            resource_prop.text = producer.resource
        # Stored properties (skip resource and managed kdenlive keys)
        for name, value in producer.properties.items():
            if name == "resource":
                continue
            if name in _MANAGED_PROPS:
                continue  # will be written fresh below
            prop = ET.SubElement(p_elem, "property")
            prop.set("name", name)
            prop.text = value
        # Serializer-managed kdenlive metadata (always regenerated)
        _set_prop(p_elem, "kdenlive:uuid", _producer_uuid(producer.id))
        _set_prop(p_elem, "kdenlive:id", str(kdenlive_id))
        _set_prop(p_elem, "kdenlive:clip_type", _clip_type(producer.properties))
        _set_prop(
            p_elem,
            "kdenlive:folderid",
            producer.properties.get("kdenlive:folderid", "-1"),
        )

    # ------------------------------------------------------------------
    # Sub-spec 3: black_track background producer
    # ------------------------------------------------------------------
    bt_elem = ET.SubElement(root, "producer")
    bt_elem.set("id", "black_track")
    bt_elem.set("in", "0")
    bt_elem.set("out", "2147483646")
    _set_prop(bt_elem, "mlt_service", "color")
    _set_prop(bt_elem, "resource", "black")
    _set_prop(bt_elem, "length", "2147483647")

    # ------------------------------------------------------------------
    # Sub-spec 2: main_bin playlist (bin registration for all producers)
    # ------------------------------------------------------------------
    proj_uuid = _project_uuid(project.title)
    profile_name = (
        f"{project.profile.width}x{project.profile.height}"
        f"_fps{int(round(project.profile.fps))}"
    )
    main_bin = ET.SubElement(root, "playlist")
    main_bin.set("id", "main_bin")
    _set_prop(main_bin, "kdenlive:docproperties.version", "1.1")
    _set_prop(main_bin, "kdenlive:docproperties.profile", profile_name)
    _set_prop(main_bin, "kdenlive:docproperties.uuid", proj_uuid)
    for producer in project.producers:
        entry = ET.SubElement(main_bin, "entry")
        entry.set("producer", producer.id)
        entry.set("in", "0")
        entry.set("out", "0")

    # ------------------------------------------------------------------
    # Content playlists + sub-spec 3: paired empty playlists
    # ------------------------------------------------------------------
    for playlist in project.playlists:
        pl_elem = ET.SubElement(root, "playlist")
        pl_elem.set("id", playlist.id)
        for entry in playlist.entries:
            if entry.producer_id:
                e_elem = ET.SubElement(pl_elem, "entry")
                e_elem.set("producer", entry.producer_id)
                e_elem.set("in", str(entry.in_point))
                e_elem.set("out", str(entry.out_point))
            else:
                blank_elem = ET.SubElement(pl_elem, "blank")
                blank_elem.set("length", str(entry.out_point + 1))

        # Paired empty playlist (Kdenlive convention)
        pair_elem = ET.SubElement(root, "playlist")
        pair_elem.set("id", f"{playlist.id}_kdpair")

    # ------------------------------------------------------------------
    # Sub-spec 3: Tractor with black_track, paired tracks, transitions
    # ------------------------------------------------------------------
    # Determine which tracks to include and their types
    track_type_map: dict[str, str] = {t.id: t.track_type for t in project.tracks}

    if project.tractor is not None or project.playlists:
        tractor_elem = ET.SubElement(root, "tractor")

        if project.tractor is not None:
            for k, v in project.tractor.items():
                tractor_elem.set(k, str(v))
            # Determine tracks source
            if project.tracks:
                tracks_source = project.tracks
            else:
                # Fall back to playlists as video tracks
                tracks_source = [
                    Track(id=pl.id, track_type="video") for pl in project.playlists
                ]
        else:
            # Auto-generate tractor
            tractor_elem.set("id", "tractor0")
            max_out = max(
                (
                    sum(
                        (e.out_point - e.in_point + 1)
                        for e in pl.entries
                        if e.producer_id
                    )
                    for pl in project.playlists
                ),
                default=0,
            )
            tractor_elem.set("in", "0")
            tractor_elem.set("out", str(max_out - 1) if max_out > 0 else "0")
            tracks_source = [
                Track(id=pl.id, track_type=track_type_map.get(pl.id, "video"))
                for pl in project.playlists
            ]

        # black_track is the first tractor track (track index 0)
        bt_track = ET.SubElement(tractor_elem, "track")
        bt_track.set("producer", "black_track")
        bt_track.set("hide", "video")

        # Content + pair tracks (track indices 1, 2, 3, 4, …)
        track_index = 1
        for track in tracks_source:
            pair_id = f"{track.id}_kdpair"

            # Content track
            t_content = ET.SubElement(tractor_elem, "track")
            t_content.set("producer", track.id)
            if track.track_type == "audio":
                t_content.set("hide", "video")

            # Paired empty track
            t_pair = ET.SubElement(tractor_elem, "track")
            t_pair.set("producer", pair_id)
            if track.track_type == "audio":
                t_pair.set("hide", "video")

            # Internal transition for this track pair
            trans_elem = ET.SubElement(tractor_elem, "transition")
            if track.track_type == "audio":
                _set_prop(trans_elem, "mlt_service", "mix")
                _set_prop(trans_elem, "a_track", "0")
                _set_prop(trans_elem, "b_track", str(track_index))
                _set_prop(trans_elem, "always_active", "1")
                _set_prop(trans_elem, "sum", "1")
            else:
                _set_prop(trans_elem, "mlt_service", "frei0r.cairoblend")
                _set_prop(trans_elem, "a_track", "0")
                _set_prop(trans_elem, "b_track", str(track_index))
                _set_prop(trans_elem, "always_active", "1")

            track_index += 2  # content + pair occupy two slots each

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
    # Opaque elements – re-insert verbatim
    # ------------------------------------------------------------------
    for opaque in project.opaque_elements:
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
