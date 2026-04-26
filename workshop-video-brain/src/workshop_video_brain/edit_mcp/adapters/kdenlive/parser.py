"""Kdenlive XML parser.  Reads a .kdenlive file into a KdenliveProject model.

The parser handles both the legacy "flat single-tractor" shape and the modern
Kdenlive 25.x shape (per-track tractors + UUID main sequence + projectTractor
wrapper).  Unknown XML elements are preserved verbatim as OpaqueElement
objects for round-trip safety.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    EntryFilter,
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SequenceTransition,
    Track,
)

logger = logging.getLogger(__name__)

_UUID_TRACTOR_RE = re.compile(
    r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$"
)
_TRACK_TRACTOR_PREFIX = "tractor_track_"
_PROJECT_TRACTOR_ID = "tractor_project"

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


def _parse_sequence_transition(trans_elem: ET.Element) -> SequenceTransition | None:
    """Convert a ``<transition>`` element from the main sequence tractor
    into a :class:`SequenceTransition`, or return None for auto-internal
    transitions (per-track ``mix``/``qtblend`` with ``internal_added=237``)
    that the serializer rebuilds from the track list.
    """
    properties: dict[str, str] = {}
    for child in trans_elem:
        if child.tag == "property":
            name = child.get("name", "")
            value = child.text or ""
            properties[name] = value

    # Skip auto-internal transitions -- the serializer recreates these
    # automatically based on ``project.tracks``.  Capturing them as
    # SequenceTransitions would duplicate them on re-serialize.
    if properties.get("internal_added") == "237":
        return None

    try:
        a_track = int(properties.get("a_track", "0"))
        b_track = int(properties.get("b_track", "0"))
    except (TypeError, ValueError):
        return None

    in_attr = trans_elem.get("in")
    out_attr = trans_elem.get("out")
    try:
        in_frame = int(in_attr) if in_attr is not None else 0
        out_frame = int(out_attr) if out_attr is not None else 0
    except ValueError:
        # Timecode-format in/out -- skip for now (rare in v25 saves).
        return None

    extra_props = {
        k: v for k, v in properties.items()
        if k not in {"a_track", "b_track", "mlt_service", "kdenlive_id"}
    }
    return SequenceTransition(
        id=trans_elem.get("id", ""),
        a_track=a_track,
        b_track=b_track,
        in_frame=in_frame,
        out_frame=out_frame,
        mlt_service=properties.get("mlt_service", ""),
        kdenlive_id=properties.get("kdenlive_id", ""),
        properties=extra_props,
    )


def _parse_entry_filter(filter_elem: ET.Element) -> EntryFilter:
    """Parse a ``<filter>`` child of a playlist ``<entry>`` into an
    :class:`EntryFilter` so it round-trips through the model."""
    properties: dict[str, str] = {}
    zone_in = None
    zone_out = None
    for child in filter_elem:
        if child.tag != "property":
            continue
        name = child.get("name", "")
        value = child.text or ""
        if name == "kdenlive:zone_in":
            try:
                zone_in = int(value)
            except (TypeError, ValueError):
                pass
            continue
        if name == "kdenlive:zone_out":
            try:
                zone_out = int(value)
            except (TypeError, ValueError):
                pass
            continue
        properties[name] = value
    in_attr = filter_elem.get("in")
    out_attr = filter_elem.get("out")
    in_frame = None
    out_frame = None
    try:
        if in_attr is not None:
            in_frame = int(in_attr)
        if out_attr is not None:
            out_frame = int(out_attr)
    except ValueError:
        pass  # leave None if the attribute is a timecode rather than int
    return EntryFilter(
        id=filter_elem.get("id", ""),
        in_frame=in_frame,
        out_frame=out_frame,
        zone_in_frame=zone_in,
        zone_out_frame=zone_out,
        properties=properties,
    )


def _parse_playlist(elem: ET.Element) -> tuple[Playlist, list[OpaqueElement]]:
    playlist_id = elem.get("id", "")
    entries: list[PlaylistEntry] = []
    opaques: list[OpaqueElement] = []
    for child in elem:
        if child.tag == "entry":
            entry_filters: list[EntryFilter] = [
                _parse_entry_filter(c) for c in child if c.tag == "filter"
            ]
            entries.append(
                PlaylistEntry(
                    producer_id=child.get("producer", ""),
                    in_point=int(child.get("in", "0")),
                    out_point=int(child.get("out", "0")),
                    filters=entry_filters,
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


def _classify_tractor(elem: ET.Element) -> str:
    """Classify a top-level ``<tractor>`` element.

    Returns one of:
      * ``"per_track"`` -- wraps exactly two ``<playlist>`` references
        (one content + one paired empty); represents one timeline track.
      * ``"sequence"`` -- the main sequence (UUID id + ``kdenlive:uuid`` prop).
      * ``"project"`` -- the outer wrapper (``kdenlive:projectTractor=1``).
      * ``"legacy"`` -- the old flat-shape single tractor.
    """
    tractor_id = elem.get("id", "")
    props = {
        c.get("name", ""): (c.text or "")
        for c in elem
        if c.tag == "property"
    }
    if props.get("kdenlive:projectTractor") == "1" or tractor_id == _PROJECT_TRACTOR_ID:
        return "project"
    if _UUID_TRACTOR_RE.match(tractor_id) or "kdenlive:uuid" in props:
        return "sequence"
    if tractor_id.startswith(_TRACK_TRACTOR_PREFIX):
        return "per_track"
    track_children = elem.findall("track")
    if len(track_children) == 2:
        producer_refs = [t.get("producer", "") for t in track_children]
        # A legitimate per-track tractor pairs one content playlist with its
        # ``*_kdpair`` empty companion.  Anything else (e.g. a legacy single
        # tractor that happens to reference exactly two playlists) is *not*
        # a per-track tractor.
        if any(ref.endswith("_kdpair") for ref in producer_refs):
            return "per_track"
    return "legacy"


def parse_project(path: Path) -> KdenliveProject:
    """Parse a .kdenlive XML file and return a KdenliveProject.

    Handles both the legacy flat-tractor shape and the v25 multi-tractor shape.
    Unknown XML elements are captured as OpaqueElement objects.  This function
    never raises; warnings are logged on unsupported constructs.
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
    sequence_transitions: list[SequenceTransition] = []
    # Map of timewarp variant producer id -> (source_id, speed) so we can
    # round-trip ``PlaylistEntry.speed``.  The serializer emits one variant
    # producer per (source, speed) pair and rewrites the entry's producer
    # ref to point at it; we reverse that here.
    timewarp_variants: dict[str, tuple[str, float]] = {}

    # Pre-scan tractors to know which playlist ids are "B" (paired empty) playlists
    # in the v25 shape, so we don't accidentally treat them as content tracks.
    paired_b_playlist_ids: set[str] = set()
    track_tractor_to_a_playlist: dict[str, tuple[str, str]] = {}
    for tractor_elem in root.findall("tractor"):
        if _classify_tractor(tractor_elem) != "per_track":
            continue
        track_children = tractor_elem.findall("track")
        if len(track_children) != 2:
            continue
        a_id = track_children[0].get("producer", "")
        b_id = track_children[1].get("producer", "")
        # Determine track type from the hide attribute (consistent on both
        # sub-tracks; "video" → audio track, "audio" → video track).
        hide = track_children[0].get("hide", "") or track_children[1].get("hide", "")
        if hide == "video":
            track_type = "audio"
        elif hide == "audio":
            track_type = "video"
        else:
            track_type = "video"
        paired_b_playlist_ids.add(b_id)
        if a_id:
            track_tractor_to_a_playlist[tractor_elem.get("id", "")] = (a_id, track_type)

    for elem in root:
        tag = elem.tag

        if tag == "profile":
            profile = _parse_profile(elem)

        elif tag in ("producer", "chain"):
            producer_id = elem.get("id", "")
            # Skip the serializer-generated background producer
            if producer_id == "black_track":
                continue
            # Skip the bin twin of a chain -- it duplicates the timeline chain
            # and would otherwise show up as a second producer in the model.
            # The serializer emits twins with a ``_kdbin`` suffix; legacy
            # ``_bin`` suffix is also recognised for round-trip compatibility
            # with files written before that rename.
            if producer_id.endswith("_kdbin") or producer_id.endswith("_bin"):
                continue
            # Detect timewarp variants: serializer emits these as separate
            # producers with mlt_service=timewarp, ids of the form
            # ``<source>_speed_<token>``.  Don't store them as producers --
            # the serializer rebuilds them when needed.  Instead remember
            # the variant->(source, speed) mapping so we can fix up
            # playlist entries below.
            try:
                tmp_props = {
                    c.get("name", ""): (c.text or "")
                    for c in elem
                    if c.tag == "property"
                }
                if tmp_props.get("mlt_service") == "timewarp":
                    try:
                        speed = float(tmp_props.get("warp_speed", "1.0"))
                    except (TypeError, ValueError):
                        speed = 1.0
                    # Source id is the variant id stripped of its
                    # ``_speed_<token>`` suffix.
                    if "_speed_" in producer_id:
                        source_id = producer_id.rsplit("_speed_", 1)[0]
                        timewarp_variants[producer_id] = (source_id, speed)
                    continue
                producers.append(_parse_producer(elem))
            except Exception as exc:
                logger.warning("Skipping malformed <%s>: %s", tag, exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "playlist":
            playlist_id = elem.get("id", "")
            # Skip serializer-generated infrastructure playlists
            if playlist_id == "main_bin" or playlist_id.endswith("_kdpair"):
                continue
            if playlist_id in paired_b_playlist_ids:
                continue
            try:
                playlist, child_opaques = _parse_playlist(elem)
                playlists.append(playlist)
                opaque_elements.extend(child_opaques)
            except Exception as exc:
                logger.warning("Skipping malformed <playlist>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "tractor":
            classification = _classify_tractor(elem)
            try:
                if classification == "per_track":
                    a_id_type = track_tractor_to_a_playlist.get(elem.get("id", ""))
                    if a_id_type:
                        a_id, track_type = a_id_type
                        # Avoid duplicate entries if the same playlist is
                        # already tracked.
                        if not any(t.id == a_id for t in tracks):
                            tracks.append(Track(id=a_id, track_type=track_type))
                elif classification == "sequence":
                    # Capture the sequence's in/out as the project tractor metadata
                    # so the model retains timeline length info.  Only the first
                    # sequence wins.
                    if tractor is None:
                        tractor = {k: v for k, v in elem.attrib.items()}
                    # Reconstruct user-added cross-track transitions
                    # (cross-dissolves, wipes, slides) as SequenceTransition
                    # so they round-trip.  Auto-internal transitions per
                    # track (mix/qtblend with internal_added=237) are
                    # auto-rebuilt by the serializer based on the track
                    # list and must NOT be captured here -- doing so would
                    # double-emit them.
                    for trans_elem in elem.findall("transition"):
                        st = _parse_sequence_transition(trans_elem)
                        if st is not None:
                            sequence_transitions.append(st)
                elif classification == "project":
                    # Wrapper -- nothing to extract; serializer will rebuild it.
                    pass
                else:  # legacy
                    tractor_dict, tractor_tracks, tractor_opaques = _parse_tractor(elem)
                    if tractor is None:
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

    # Re-route any playlist entries that referenced a timewarp variant
    # back to the source chain, with ``speed`` set so the serializer
    # rebuilds the variant on next emit.
    if timewarp_variants:
        for playlist in playlists:
            for entry in playlist.entries:
                mapping = timewarp_variants.get(entry.producer_id)
                if mapping is not None:
                    source_id, speed = mapping
                    entry.producer_id = source_id
                    entry.speed = speed

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
        sequence_transitions=sequence_transitions,
    )
