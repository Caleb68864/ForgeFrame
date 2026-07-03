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
        # MLT <link> children (chain-only).  Each link is a service + properties.
        for link in producer.links:
            link_elem = ET.SubElement(p_elem, "link")
            link_elem.set("mlt_service", link.mlt_service)
            for name, value in link.properties.items():
                lprop = ET.SubElement(link_elem, "property")
                lprop.set("name", name)
                lprop.text = value

    # ------------------------------------------------------------------
    # Sub-spec 3: black_track background producer
    # ------------------------------------------------------------------
    # Bound the background to the actual timeline length so that a render or
    # `-consumer null` stops at the content instead of ~2e9 frames.  A clip
    # that has been sped up (timewarp) shortens the timeline, and this is what
    # makes the shorter duration observable to a fixed-`out` render.
    content_out = _content_out(project)
    bt_elem = ET.SubElement(root, "producer")
    bt_elem.set("id", "black_track")
    bt_elem.set("in", "0")
    bt_elem.set("out", str(content_out))
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
    # Modern Kdenlive (24.x/25.x) reads guides from a JSON docproperties/
    # sequenceproperties property, not the legacy top-level <guide> elements.
    # Emit the JSON here (main_bin) for pre-sequence docs; the tractor also gets
    # kdenlive:sequenceproperties.guides below.  Legacy <guide> elements are
    # still written (harmless) for our own round-trip.
    if project.guides:
        try:
            from workshop_video_brain.edit_mcp.pipelines.guides import (
                guides_docproperties_json,
            )
            guides_json = guides_docproperties_json(project)
            _set_prop(main_bin, "kdenlive:docproperties.guides", guides_json)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise guides JSON: %s", exc)
    # Subtitle tracks: modern Kdenlive reads the Subtitles panel from a
    # docproperties.subtitlesList JSON (mirrored on the sequence tractor below)
    # plus an activeSubtitleIndex.  The rendered pixels come from the
    # avfilter.subtitles filter emitted on the tractor.
    if project.subtitles:
        try:
            from workshop_video_brain.edit_mcp.pipelines.subtitle_track import (
                active_subtitle_index,
                subtitles_list_json,
            )
            _set_prop(
                main_bin,
                "kdenlive:docproperties.subtitlesList",
                subtitles_list_json(project),
            )
            _set_prop(
                main_bin,
                "kdenlive:docproperties.activeSubtitleIndex",
                active_subtitle_index(project),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not serialise subtitlesList JSON: %s", exc)
    # ---- PROXY / doc-property bag (round-tripped, suffix-keyed) ----
    # Non-managed ``kdenlive:docproperties.*`` settings (notably proxy: enableproxy,
    # proxyparams, proxyextension, generateproxy, proxyminsize, ...).  Managed keys
    # (version/profile/uuid/guides/subtitlesList/activeSubtitleIndex) are emitted
    # above and excluded by the parser, so no duplicates arise here.
    for suffix, value in project.docproperties.items():
        _set_prop(main_bin, f"kdenlive:docproperties.{suffix}", str(value))
    # ---- end PROXY / doc-property bag ----
    for producer in project.producers:
        entry = ET.SubElement(main_bin, "entry")
        entry.set("producer", producer.id)
        entry.set("in", "0")
        entry.set("out", "0")

    # ------------------------------------------------------------------
    # Content playlists + sub-spec 3: paired empty playlists
    # ------------------------------------------------------------------
    # Clip effects are relocated from the flat opaque store into the clip
    # <entry> they target (§1.1 filter-placement fix).
    clip_filters, consumed_filter_ids = _extract_clip_filters(project)
    # Track-level audio/effect filters are relocated into the track's <playlist>
    # (after its entries) -- the only placement melt applies track-wide
    # (§3 "Track-level audio", render-verified).
    track_filters, consumed_track_filter_ids = _extract_track_filters(project)
    for track_index, playlist in enumerate(project.playlists):
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

        # Paired empty playlist (Kdenlive convention)
        pair_elem = ET.SubElement(root, "playlist")
        pair_elem.set("id", f"{playlist.id}_kdpair")

    # ------------------------------------------------------------------
    # Sub-spec 3: Tractor with black_track, paired tracks, transitions
    # ------------------------------------------------------------------
    # Determine which tracks to include and their types
    track_type_map: dict[str, str] = {t.id: t.track_type for t in project.tracks}

    # Track mute/visibility directives override the default hide attribute.
    hide_by_track, consumed_hide_ids = _hide_directives(project)

    tractor_elem: ET.Element | None = None
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
            if track.id in hide_by_track:
                hide_val = hide_by_track[track.id]
                if hide_val:
                    t_content.set("hide", hide_val)
            elif track.track_type == "audio":
                t_content.set("hide", "video")

            # Paired empty track
            t_pair = ET.SubElement(tractor_elem, "track")
            t_pair.set("producer", pair_id)
            if track.track_type == "audio":
                t_pair.set("hide", "video")

            # Internal transition for this track pair (Kdenlive-managed).
            # Crossfade overlay tracks (created by AddTransition) deliberately
            # get NO always_active compositor: their compositing is driven by
            # the explicit luma mix transition instead, so the dissolve animates
            # instead of being flattened to a fixed blend.
            if "_xfade" not in track.id:
                trans_elem = ET.SubElement(tractor_elem, "transition")
                if track.track_type == "audio":
                    _set_prop(trans_elem, "mlt_service", "mix")
                    _set_prop(trans_elem, "a_track", "0")
                    _set_prop(trans_elem, "b_track", str(track_index))
                    _set_prop(trans_elem, "always_active", "1")
                    _set_prop(trans_elem, "sum", "1")
                    _set_prop(trans_elem, "internal_added", "237")
                else:
                    _set_prop(trans_elem, "mlt_service", "frei0r.cairoblend")
                    _set_prop(trans_elem, "a_track", "0")
                    _set_prop(trans_elem, "b_track", str(track_index))
                    _set_prop(trans_elem, "always_active", "1")
                    _set_prop(trans_elem, "internal_added", "237")

            track_index += 2  # content + pair occupy two slots each

        # Modern Kdenlive stores guides as JSON on the active sequence tractor.
        if project.guides:
            try:
                from workshop_video_brain.edit_mcp.pipelines.guides import (
                    guides_docproperties_json,
                )
                _set_prop(
                    tractor_elem,
                    "kdenlive:sequenceproperties.guides",
                    guides_docproperties_json(project),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Could not serialise sequence guides JSON: %s", exc)

        # Subtitle tracks: one avfilter.subtitles filter per track attached to
        # the timeline tractor (the only place MLT/melt render subtitle pixels
        # -- proven headless), plus the sequenceproperties mirror of the list.
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
    # Guides (legacy top-level elements; harmless, kept for round-trip)
    # ------------------------------------------------------------------
    for guide in project.guides:
        g_elem = ET.SubElement(root, "guide")
        g_elem.set("position", str(guide.position))
        g_elem.set("comment", guide.label)
        if guide.category:
            g_elem.set("type", guide.category)

    # ------------------------------------------------------------------
    # Opaque elements – re-insert, honouring position_hint.  Clip filters and
    # hide directives have already been consumed above; tractor-hinted content
    # (transitions/filters) is nested back inside the <tractor> so MLT applies
    # it, everything else goes to the document root.
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
