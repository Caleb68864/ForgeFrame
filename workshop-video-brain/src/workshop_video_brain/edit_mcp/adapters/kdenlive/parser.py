"""Kdenlive XML parser.  Reads a .kdenlive file into a KdenliveProject model.

Unknown XML elements are preserved verbatim as OpaqueElement objects for
round-trip safety.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)

logger = logging.getLogger(__name__)

# Tags that this parser handles explicitly (lowercase).
_KNOWN_TAGS = {
    "mlt",
    "profile",
    "producer",
    "playlist",
    "tractor",
    "track",
    "entry",
    "property",
    # Kdenlive guide / marker elements that appear as children of mlt
    "kdenlive:guide",
    "guide",
}


def _elem_to_opaque(elem: ET.Element, position_hint: str | None = None) -> OpaqueElement:
    return OpaqueElement(
        tag=elem.tag,
        xml_string=ET.tostring(elem, encoding="unicode"),
        position_hint=position_hint,
    )


def _parse_profile(elem: ET.Element) -> ProjectProfile:
    try:
        fps_num = int(elem.get("frame_rate_num", "25"))
        fps_den = int(elem.get("frame_rate_den", "1"))
        fps = fps_num / fps_den if fps_den else 25.0
        return ProjectProfile(
            width=int(elem.get("width", "1920")),
            height=int(elem.get("height", "1080")),
            fps=fps,
            colorspace=elem.get("colorspace"),
        )
    except Exception as exc:
        logger.warning("Could not parse <profile>: %s", exc)
        return ProjectProfile()


def _parse_producer(elem: ET.Element) -> Producer:
    producer_id = elem.get("id", "")
    props: dict[str, str] = {}
    for child in elem:
        if child.tag == "property":
            name = child.get("name", "")
            value = child.text or ""
            props[name] = value
    resource = props.get("resource", "")
    return Producer(id=producer_id, resource=resource, properties=props)


def _parse_playlist(elem: ET.Element) -> tuple[Playlist, list[OpaqueElement]]:
    playlist_id = elem.get("id", "")
    entries: list[PlaylistEntry] = []
    opaques: list[OpaqueElement] = []
    for child in elem:
        if child.tag == "entry":
            entries.append(
                PlaylistEntry(
                    producer_id=child.get("producer", ""),
                    in_point=int(child.get("in", "0")),
                    out_point=int(child.get("out", "0")),
                )
            )
        elif child.tag == "blank":
            # Represent gaps as PlaylistEntry with empty producer_id
            length = int(child.get("length", "0"))
            entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=length - 1))
        else:
            opaques.append(_elem_to_opaque(child, position_hint=f"playlist:{playlist_id}"))
            logger.warning("Unsupported element <%s> inside playlist '%s'", child.tag, playlist_id)
    return Playlist(id=playlist_id, entries=entries), opaques


def _parse_tractor(elem: ET.Element) -> tuple[dict, list[Track], list[OpaqueElement]]:
    tractor_dict: dict = {k: v for k, v in elem.attrib.items()}
    tracks: list[Track] = []
    opaques: list[OpaqueElement] = []
    for child in elem:
        if child.tag == "track":
            producer_ref = child.get("producer", "")
            # Skip serializer-generated infrastructure tracks
            if producer_ref == "black_track" or producer_ref.endswith("_kdpair"):
                continue
            # Determine type from hide attribute
            hide = child.get("hide", "")
            if hide == "video":
                track_type = "audio"
            elif hide == "audio":
                track_type = "video"
            else:
                track_type = "video"
            tracks.append(Track(id=producer_ref, track_type=track_type))
        elif child.tag in ("transition", "filter"):
            opaques.append(_elem_to_opaque(child, position_hint="tractor"))
        else:
            opaques.append(_elem_to_opaque(child, position_hint="tractor"))
            logger.warning("Unsupported element <%s> inside tractor", child.tag)
    return tractor_dict, tracks, opaques


def _parse_guide(elem: ET.Element) -> Guide | None:
    try:
        pos_str = elem.get("position") or elem.get("time") or elem.get("pos") or "0"
        # Position might be a frame count or a timecode; store as int
        position = int(float(pos_str))
        label = elem.get("comment") or elem.get("label") or elem.text or ""
        category = elem.get("type") or elem.get("category")
        comment = elem.get("comment") if "comment" not in (label,) else None
        return Guide(position=position, label=label, category=category, comment=comment)
    except Exception as exc:
        logger.warning("Could not parse guide element: %s", exc)
        return None


def parse_project(path: Path) -> KdenliveProject:
    """Parse a .kdenlive XML file and return a KdenliveProject.

    Unknown XML elements are captured as OpaqueElement objects.
    This function never raises; warnings are logged on unsupported constructs.
    """
    path = Path(path)
    try:
        tree = ET.parse(path)
    except FileNotFoundError as exc:
        logger.error("File not found: %s: %s", path, exc)
        return KdenliveProject()
    except ET.ParseError as exc:
        logger.error("XML parse error in %s: %s", path, exc)
        return KdenliveProject()

    root = tree.getroot()

    version = root.get("version", "")
    title = root.get("title", "")

    profile = ProjectProfile()
    producers: list[Producer] = []
    playlists: list[Playlist] = []
    tracks: list[Track] = []
    tractor: dict | None = None
    guides: list[Guide] = []
    opaque_elements: list[OpaqueElement] = []

    for elem in root:
        tag = elem.tag

        if tag == "profile":
            profile = _parse_profile(elem)

        elif tag == "producer":
            producer_id = elem.get("id", "")
            # Skip the serializer-generated background producer
            if producer_id == "black_track":
                continue
            try:
                producers.append(_parse_producer(elem))
            except Exception as exc:
                logger.warning("Skipping malformed <producer>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "playlist":
            playlist_id = elem.get("id", "")
            # Skip serializer-generated infrastructure playlists
            if playlist_id == "main_bin" or playlist_id.endswith("_kdpair"):
                continue
            try:
                playlist, child_opaques = _parse_playlist(elem)
                playlists.append(playlist)
                opaque_elements.extend(child_opaques)
            except Exception as exc:
                logger.warning("Skipping malformed <playlist>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "tractor":
            try:
                tractor_dict, tractor_tracks, tractor_opaques = _parse_tractor(elem)
                tractor = tractor_dict
                tracks.extend(tractor_tracks)
                opaque_elements.extend(tractor_opaques)
            except Exception as exc:
                logger.warning("Skipping malformed <tractor>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag in ("kdenlive:guide", "guide"):
            guide = _parse_guide(elem)
            if guide is not None:
                guides.append(guide)
            else:
                opaque_elements.append(_elem_to_opaque(elem, position_hint="guides"))

        else:
            # Unknown / unsupported element – preserve opaquely
            opaque_elements.append(_elem_to_opaque(elem))
            logger.warning(
                "Unknown element <%s> preserved as opaque node", tag
            )

    return KdenliveProject(
        version=version,
        title=title,
        profile=profile,
        producers=producers,
        tracks=tracks,
        playlists=playlists,
        tractor=tractor,
        guides=guides,
        opaque_elements=opaque_elements,
    )
