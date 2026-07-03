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
    Link,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SubtitleTrack,
    Track,
)

logger = logging.getLogger(__name__)


class ProjectParseError(Exception):
    """Raised when a .kdenlive file cannot be read or parsed.

    Carries the offending ``path`` and the underlying ``cause`` so callers can
    return a precise error instead of silently proceeding with an empty
    project (which would let a downstream patch overwrite a corrupt-but-
    recoverable file).
    """

    def __init__(self, path: Path, cause: Exception):
        self.path = Path(path)
        self.cause = cause
        super().__init__(f"Failed to parse project '{self.path}': {cause}")


# Tags that this parser handles explicitly (lowercase).
_KNOWN_TAGS = {
    "mlt",
    "profile",
    "producer",
    "chain",
    "link",
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


def _parse_chain(elem: ET.Element) -> Producer:
    """Parse a ``<chain>`` (producer + MLT ``<link>`` children) into a Producer.

    Round-trips the chain form the serializer emits for the native
    ``timeremap`` engine: top-level ``<property>`` children populate the
    producer, each ``<link>`` becomes a :class:`Link`, and the chain's ``out``
    attribute is preserved on ``chain_out``.  Kept deliberately independent of
    ``_parse_producer`` so the chain-only vocabulary stays isolated.
    """
    producer_id = elem.get("id", "")
    props: dict[str, str] = {}
    links: list[Link] = []
    for child in elem:
        if child.tag == "property":
            props[child.get("name", "")] = child.text or ""
        elif child.tag == "link":
            link_props: dict[str, str] = {}
            for lchild in child:
                if lchild.tag == "property":
                    link_props[lchild.get("name", "")] = lchild.text or ""
            links.append(
                Link(
                    mlt_service=child.get("mlt_service", ""),
                    properties=link_props,
                )
            )
    chain_out_raw = elem.get("out")
    chain_out = int(chain_out_raw) if chain_out_raw is not None else None
    return Producer(
        id=producer_id,
        resource=props.get("resource", ""),
        properties=props,
        links=links,
        chain_out=chain_out,
    )


def _parse_playlist(
    elem: ET.Element, track_index: int = 0
) -> tuple[Playlist, list[OpaqueElement]]:
    playlist_id = elem.get("id", "")
    entries: list[PlaylistEntry] = []
    opaques: list[OpaqueElement] = []
    real_index = 0
    for child in elem:
        if child.tag == "entry":
            entries.append(
                PlaylistEntry(
                    producer_id=child.get("producer", ""),
                    in_point=int(child.get("in", "0")),
                    out_point=int(child.get("out", "0")),
                )
            )
            # Clip effects are stored by real Kdenlive as <filter> children of
            # the <entry> (§1.2).  Read them into the flat opaque store, tagged
            # with the (track, clip) association attributes the effect-stack API
            # and serializer use so they round-trip back into the entry.
            for sub in child:
                if sub.tag != "filter":
                    continue
                felem = ET.fromstring(ET.tostring(sub, encoding="unicode"))
                felem.set("track", str(track_index))
                felem.set("clip_index", str(real_index))
                opaques.append(
                    OpaqueElement(
                        tag="filter",
                        xml_string=ET.tostring(felem, encoding="unicode"),
                        position_hint="after_tractor",
                    )
                )
            real_index += 1
        elif child.tag == "blank":
            # Represent gaps as PlaylistEntry with empty producer_id
            length = int(child.get("length", "0"))
            entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=length - 1))
        elif child.tag == "filter":
            # Track-level effects are stored by real Kdenlive/MLT as <filter>
            # direct children of the track <playlist> (§3 "Track-level audio").
            # Tag with the track association attribute (no clip_index) so they
            # round-trip back into the playlist.
            felem = ET.fromstring(ET.tostring(child, encoding="unicode"))
            felem.set("track", str(track_index))
            opaques.append(
                OpaqueElement(
                    tag="filter",
                    xml_string=ET.tostring(felem, encoding="unicode"),
                    position_hint="track",
                )
            )
        else:
            opaques.append(_elem_to_opaque(child, position_hint=f"playlist:{playlist_id}"))
            logger.warning("Unsupported element <%s> inside playlist '%s'", child.tag, playlist_id)
    return Playlist(id=playlist_id, entries=entries), opaques


# ``kdenlive:docproperties.*`` suffixes the serializer regenerates from model
# state.  Excluded on parse so they don't duplicate in the docproperties bag.
_MANAGED_DOCPROPERTY_SUFFIXES = frozenset(
    {
        "version",
        "profile",
        "uuid",
        "guides",
        "subtitlesList",
        "activeSubtitleIndex",
    }
)

_DOCPROP_PREFIX = "kdenlive:docproperties."


def _parse_docproperties(elem: ET.Element) -> dict[str, str]:
    """Read non-managed ``kdenlive:docproperties.*`` off the main_bin playlist.

    Returns a suffix-keyed dict (e.g. ``{"enableproxy": "1"}``).  Proxy settings
    live here; the serializer re-emits them so they round-trip.
    """
    docprops: dict[str, str] = {}
    for child in elem:
        if child.tag != "property":
            continue
        name = child.get("name", "")
        if not name.startswith(_DOCPROP_PREFIX):
            continue
        suffix = name[len(_DOCPROP_PREFIX):]
        if suffix in _MANAGED_DOCPROPERTY_SUFFIXES:
            continue
        docprops[suffix] = child.text or ""
    return docprops


# Tractor <property> keys the serializer regenerates from KdenliveProject state.
# Skipping them on parse prevents a duplicate on the next serialize.
_REGENERATED_TRACTOR_PROPS = frozenset(
    {
        "kdenlive:sequenceproperties.guides",
        "kdenlive:sequenceproperties.subtitlesList",
    }
)


def _filter_props(elem: ET.Element) -> dict[str, str]:
    """Return the ``<property name=...>`` map of a filter/transition element."""
    props: dict[str, str] = {}
    for prop in elem:
        if prop.tag == "property":
            props[prop.get("name", "")] = prop.text or ""
    return props


def _subtitle_from_filter(elem: ET.Element) -> SubtitleTrack | None:
    """Build a SubtitleTrack from an ``avfilter.subtitles`` tractor filter."""
    props = _filter_props(elem)
    if props.get("mlt_service") != "avfilter.subtitles":
        return None
    kid = props.get("kdenlive:id") or elem.get("id", "").replace("subtitle_", "")
    try:
        sub_id = int(kid)
    except (TypeError, ValueError):
        sub_id = 0
    return SubtitleTrack(
        id=sub_id,
        name="Subtitle",
        file=props.get("av.filename", ""),
        style=props.get("av.force_style") or None,
    )


def _parse_tractor(
    elem: ET.Element,
) -> tuple[dict, list[Track], list[OpaqueElement], list[SubtitleTrack]]:
    tractor_dict: dict = {k: v for k, v in elem.attrib.items()}
    tracks: list[Track] = []
    opaques: list[OpaqueElement] = []
    subtitles: list[SubtitleTrack] = []
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
        elif child.tag == "filter":
            # Real subtitle tracks are avfilter.subtitles filters on the tractor;
            # read them into first-class SubtitleTrack objects (round-trip) rather
            # than losing them into the opaque store.
            sub = _subtitle_from_filter(child)
            if sub is not None:
                subtitles.append(sub)
            else:
                opaques.append(_elem_to_opaque(child, position_hint="tractor"))
        elif child.tag == "transition":
            opaques.append(_elem_to_opaque(child, position_hint="tractor"))
        elif child.tag == "property":
            # Tractor sequence properties.  The serializer regenerates the guides
            # and subtitlesList JSON from model state, so dropping those two here
            # avoids a duplicate property on the next write; any other sequence
            # property (groups, activeTrack, ...) is preserved verbatim.
            if child.get("name") in _REGENERATED_TRACTOR_PROPS:
                continue
            opaques.append(_elem_to_opaque(child, position_hint="tractor"))
        else:
            opaques.append(_elem_to_opaque(child, position_hint="tractor"))
            logger.warning("Unsupported element <%s> inside tractor", child.tag)
    return tractor_dict, tracks, opaques, subtitles


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


def parse_project(path: Path, missing_ok: bool = False) -> KdenliveProject:
    """Parse a .kdenlive XML file and return a KdenliveProject.

    Unknown XML elements are captured as OpaqueElement objects.  Individual
    malformed *sub*-elements are still tolerated (logged + kept opaque).

    On a missing file or an unparseable document the default behaviour is to
    raise :class:`ProjectParseError` -- returning an empty project here is
    dangerous because a downstream tool would then "patch" nothing and
    serialize it over a corrupt-but-recoverable file.

    Args:
        path: Path to the .kdenlive file.
        missing_ok: If True, return an empty ``KdenliveProject`` instead of
            raising when the file is missing or unparseable.  Reserved for
            read-only/best-effort callers (resource browsing, profile sniffing)
            that genuinely want a graceful empty fallback.

    Raises:
        ProjectParseError: If the file cannot be read/parsed and
            ``missing_ok`` is False.
    """
    path = Path(path)
    try:
        tree = ET.parse(path)
    except FileNotFoundError as exc:
        logger.error("File not found: %s: %s", path, exc)
        if missing_ok:
            return KdenliveProject()
        raise ProjectParseError(path, exc) from exc
    except ET.ParseError as exc:
        logger.error("XML parse error in %s: %s", path, exc)
        if missing_ok:
            return KdenliveProject()
        raise ProjectParseError(path, exc) from exc

    root = tree.getroot()

    version = root.get("version", "")
    title = root.get("title", "")

    profile = ProjectProfile()
    producers: list[Producer] = []
    playlists: list[Playlist] = []
    tracks: list[Track] = []
    tractor: dict | None = None
    guides: list[Guide] = []
    subtitles: list[SubtitleTrack] = []
    docproperties: dict[str, str] = {}
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

        elif tag == "chain":
            try:
                producers.append(_parse_chain(elem))
            except Exception as exc:
                logger.warning("Skipping malformed <chain>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "playlist":
            playlist_id = elem.get("id", "")
            # Skip serializer-generated infrastructure playlists, but harvest the
            # non-managed docproperties (proxy settings) off main_bin first so
            # they round-trip.
            if playlist_id == "main_bin":
                docproperties.update(_parse_docproperties(elem))
                continue
            if playlist_id.endswith("_kdpair"):
                continue
            try:
                # track_index = the position this playlist will occupy in the
                # project's playlist list, matching the effect-stack / serializer
                # convention (index into project.playlists).
                playlist, child_opaques = _parse_playlist(elem, track_index=len(playlists))
                playlists.append(playlist)
                opaque_elements.extend(child_opaques)
            except Exception as exc:
                logger.warning("Skipping malformed <playlist>: %s", exc)
                opaque_elements.append(_elem_to_opaque(elem))

        elif tag == "tractor":
            try:
                tractor_dict, tractor_tracks, tractor_opaques, tractor_subs = (
                    _parse_tractor(elem)
                )
                tractor = tractor_dict
                tracks.extend(tractor_tracks)
                opaque_elements.extend(tractor_opaques)
                subtitles.extend(tractor_subs)
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
        subtitles=subtitles,
        docproperties=docproperties,
        opaque_elements=opaque_elements,
    )
