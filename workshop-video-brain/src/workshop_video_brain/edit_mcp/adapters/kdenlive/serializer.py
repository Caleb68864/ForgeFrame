"""Kdenlive project serializer.  Writes a KdenliveProject to a versioned
.kdenlive XML file under projects/working_copies/.

A snapshot of any pre-existing file at the target path is created before
writing.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.workspace import snapshot as snapshot_manager

logger = logging.getLogger(__name__)


def _next_version(directory: Path, stem: str) -> int:
    """Return the next version number for versioned .kdenlive files."""
    existing = list(directory.glob(f"{stem}_v*.kdenlive"))
    versions: list[int] = []
    for p in existing:
        # stem_vN.kdenlive
        suffix = p.stem[len(stem) + 2:]  # after "_v"
        try:
            versions.append(int(suffix))
        except ValueError:
            pass
    return max(versions, default=0) + 1


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
        # Find workspace root by traversing up to the directory that contains
        # 'projects/working_copies'
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

    # Build XML tree
    root = ET.Element("mlt")
    root.set("title", project.title)
    root.set("version", project.version)

    # Profile
    profile_elem = ET.SubElement(root, "profile")
    fps_num = int(project.profile.fps * 1000)
    fps_den = 1000
    profile_elem.set("width", str(project.profile.width))
    profile_elem.set("height", str(project.profile.height))
    profile_elem.set("frame_rate_num", str(int(project.profile.fps)))
    profile_elem.set("frame_rate_den", "1")
    if project.profile.colorspace:
        profile_elem.set("colorspace", project.profile.colorspace)

    # Producers
    for producer in project.producers:
        p_elem = ET.SubElement(root, "producer")
        p_elem.set("id", producer.id)
        # Write the resource property first (critical for Kdenlive to find media)
        if producer.resource:
            resource_prop = ET.SubElement(p_elem, "property")
            resource_prop.set("name", "resource")
            resource_prop.text = producer.resource
        for name, value in producer.properties.items():
            if name == "resource":
                continue  # already written above
            prop = ET.SubElement(p_elem, "property")
            prop.set("name", name)
            prop.text = value

    # Playlists
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
                # Gap / blank
                blank_elem = ET.SubElement(pl_elem, "blank")
                blank_elem.set("length", str(entry.out_point + 1))

    # Tractor (required for Kdenlive to recognise the timeline)
    if project.tractor is not None:
        tractor_elem = ET.SubElement(root, "tractor")
        for k, v in project.tractor.items():
            tractor_elem.set(k, str(v))
        for track in project.tracks:
            t_elem = ET.SubElement(tractor_elem, "track")
            t_elem.set("producer", track.id)
    elif project.playlists:
        # Auto-generate a tractor from playlists so Kdenlive has a timeline
        tractor_elem = ET.SubElement(root, "tractor")
        tractor_elem.set("id", "tractor0")
        # Calculate total out point from longest playlist
        max_out = 0
        for pl in project.playlists:
            pl_out = sum((e.out_point - e.in_point + 1) for e in pl.entries if e.producer_id)
            max_out = max(max_out, pl_out)
        tractor_elem.set("in", "0")
        tractor_elem.set("out", str(max_out - 1) if max_out > 0 else "0")
        for pl in project.playlists:
            t_elem = ET.SubElement(tractor_elem, "track")
            t_elem.set("producer", pl.id)

    # Guides
    for guide in project.guides:
        g_elem = ET.SubElement(root, "guide")
        g_elem.set("position", str(guide.position))
        g_elem.set("comment", guide.label)
        if guide.category:
            g_elem.set("type", guide.category)

    # Opaque elements – re-insert verbatim
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
        # Round-trip check
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
