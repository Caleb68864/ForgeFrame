"""Kdenlive project validator.

Runs structural and content checks on a KdenliveProject and returns a
ValidationReport with severity-labelled items.

The media check here is **not** its own rule. "Which producers name a file that
must be on disk, and where does a relative one resolve?" is answered once, in
``adapters/render/media_check``, because the render path enforces the same
question as a hard precondition -- and when the two were written separately they
disagreed: this validator flagged the ``color``/``black`` producer every Kdenlive
timeline carries as a missing media file, stat'd a ``timewarp`` resource with its
``<speed>:`` prefix still attached, treated remote URLs and image sequences as
missing files, and resolved relative resources against the workspace root rather
than the ``<mlt root>`` melt itself uses. So a project the renderer accepted this
rejected, and the reverse. ``tests/unit/test_media_check_reconciled.py`` is the
table of those cases, now answered identically by both.

The question is no longer only about producers. A render also opens the luma
matte of a wipe, a ``shape`` alpha mask, a subtitle sidecar and a LUT, and melt
exits 0 when any of them is gone. :func:`_model_references` collects those from
the in-memory project so this report and the renderer's hard refusal still
cannot disagree; the classification for them lives in ``media_check`` too,
in ``FILE_BACKED_PROPERTIES``.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.validation import ValidationItem, ValidationReport
from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    FILE_BACKED_SERVICES,
    element_references,
    resolve_missing_all,
    xml_properties,
)

logger = logging.getLogger(__name__)

# Sane upper bound for guide positions (10 hours at 25 fps = 9_000_000 frames)
_MAX_GUIDE_FRAMES = 9_000_000


def _producer_services(project: KdenliveProject) -> Iterator[tuple[str, str, str]]:
    """Yield ``(producer_id, mlt_service, resource)`` for every producer.

    The service is passed through exactly as the model holds it -- including
    empty. A producer that carries only a ``resource`` is defaulted by
    ``media_check.effective_service``, which is the one place that decision is
    made, so this cannot drift from what the renderer sees.
    """
    for producer in project.producers:
        service = (producer.properties.get("mlt_service") or "").strip()
        yield producer.id, service, producer.resource


def _model_references(
    project: KdenliveProject,
) -> Iterator[tuple[str, str, str, str, str]]:
    """Yield the non-producer file references an in-memory project will emit.

    The renderer's front door reads ``<filter>`` and ``<transition>`` elements
    out of the XML. The same references reach the serializer through two
    carriers, and this yields both so the two call sites see the same project:

    * ``opaque_elements`` -- every clip effect, track filter and composition is
      held as a verbatim ``<filter>``/``<transition>`` XML string (see
      ``serializer._extract_clip_filters`` / ``_extract_track_filters`` and
      ``patcher_intents._apply_add_composition``). Parsed here with the same
      reader the XML front door uses, so a luma matte or a ``shape`` mask is
      classified identically whichever side asks.
    * ``subtitles`` -- serialized as the ``avfilter.subtitles`` filter on the
      timeline tractor, whose ``av.filename`` is the sidecar melt burns in.
    """
    for opaque in project.opaque_elements:
        if opaque.tag not in ("filter", "transition"):
            continue
        try:
            element = ET.fromstring(opaque.xml_string)
        except ET.ParseError:
            # Verbatim round-trip storage: an unparseable one is a different
            # problem, and the serializer already skips it too.
            continue
        yield from element_references(
            element.tag, element.get("id", ""), xml_properties(element)
        )

    for subtitle in project.subtitles:
        yield from element_references(
            "filter",
            str(subtitle.id),
            {"mlt_service": "avfilter.subtitles", "av.filename": subtitle.file},
        )


def _media_items(
    triples: Iterable[tuple[str, str, str]],
    references: Iterable[tuple[str, str, str, str, str]],
    base: Path,
) -> list[ValidationItem]:
    """The media section of the report, entirely from the shared rule."""
    triples = list(triples)
    items: list[ValidationItem] = []

    # A producer whose service says "I am a file" but which names no file is
    # broken in a way the missing-file check cannot see. Producers outside the
    # allowlist (titles, colour, generators) have no resource *by design* and
    # must not be reported -- the old unconditional warning fired on every
    # title card in the project.
    for producer_id, service, resource in triples:
        if not (resource or "").strip() and service in FILE_BACKED_SERVICES:
            items.append(
                ValidationItem(
                    severity=ValidationSeverity.warning,
                    category="media",
                    message=(
                        f"Producer '{producer_id}' is file-backed "
                        f"(mlt_service={service}) but has no resource path."
                    ),
                    location=f"producer:{producer_id}",
                )
            )

    for miss in resolve_missing_all(triples, references, base):
        # Both the value as written and where it resolved to: for a relative
        # or speed-prefixed resource they differ, and the user needs the second.
        detail = (
            miss.resource
            if miss.resource == miss.path
            else f"{miss.resource} -> {miss.path}"
        )
        items.append(
            ValidationItem(
                severity=ValidationSeverity.error,
                category="media",
                message=f"Media file not found: {detail}",
                location=miss.location,
                path=miss.path,
            )
        )
    return items


def validate_project(
    project: KdenliveProject,
    workspace_root: Path | None = None,
) -> ValidationReport:
    """Validate *project* and return a ValidationReport.

    Checks performed:
    1. Profile has valid (positive) dimensions.
    2. At least one track is defined.
    3. Media paths exist on disk -- the shared rule from
       ``adapters/render/media_check``, resolved against the project's own
       ``<mlt root>`` and falling back to *workspace_root*. Skipped when there
       is neither.
    4. Playlist entries reference producers that exist in the project.
    5. Guide positions are within a reasonable range.
    """
    items: list[ValidationItem] = []

    # --- 1. Profile dimensions ---
    if project.profile.width <= 0 or project.profile.height <= 0:
        items.append(
            ValidationItem(
                severity=ValidationSeverity.blocking_error,
                category="profile",
                message=(
                    f"Invalid profile dimensions: "
                    f"{project.profile.width}x{project.profile.height}"
                ),
                location="profile",
            )
        )
    if project.profile.fps <= 0:
        items.append(
            ValidationItem(
                severity=ValidationSeverity.error,
                category="profile",
                message=f"Invalid fps value: {project.profile.fps}",
                location="profile",
            )
        )

    # --- 2. Tracks non-empty ---
    if not project.tracks:
        items.append(
            ValidationItem(
                severity=ValidationSeverity.warning,
                category="tracks",
                message="Project contains no tracks.",
                location="tractor",
            )
        )

    # --- 3. Media paths (the shared rule -- see the module docstring) ---
    # A relative resource resolves against the project's own ``<mlt root>``,
    # which is what melt uses; *workspace_root* is only the fallback for a
    # project built in memory, which has no root yet. With neither, there is no
    # base to resolve against and the check does not run at all.
    base = Path(project.root) if project.root else workspace_root
    if base is not None:
        items.extend(
            _media_items(
                _producer_services(project), _model_references(project), base
            )
        )

    # --- 4. Playlist entries reference valid producers ---
    producer_ids = {p.id for p in project.producers}
    for playlist in project.playlists:
        for entry in playlist.entries:
            if not entry.producer_id:
                # Gap entry – skip
                continue
            if entry.producer_id not in producer_ids:
                items.append(
                    ValidationItem(
                        severity=ValidationSeverity.error,
                        category="playlist",
                        message=(
                            f"Playlist '{playlist.id}' references unknown producer "
                            f"'{entry.producer_id}'."
                        ),
                        location=f"playlist:{playlist.id}",
                    )
                )
            # Check in <= out
            if entry.in_point > entry.out_point:
                items.append(
                    ValidationItem(
                        severity=ValidationSeverity.warning,
                        category="playlist",
                        message=(
                            f"Playlist '{playlist.id}' entry for producer "
                            f"'{entry.producer_id}' has in_point ({entry.in_point}) "
                            f"> out_point ({entry.out_point})."
                        ),
                        location=f"playlist:{playlist.id}",
                    )
                )

    # --- 5. Guide positions in reasonable range ---
    for guide in project.guides:
        if guide.position < 0 or guide.position > _MAX_GUIDE_FRAMES:
            items.append(
                ValidationItem(
                    severity=ValidationSeverity.warning,
                    category="guides",
                    message=(
                        f"Guide '{guide.label}' has position {guide.position} "
                        f"outside expected range [0, {_MAX_GUIDE_FRAMES}]."
                    ),
                    location=f"guide:{guide.position}",
                )
            )

    # Build summary
    if not items:
        summary = "No issues found."
    else:
        counts: dict[str, int] = {}
        for item in items:
            counts[str(item.severity)] = counts.get(str(item.severity), 0) + 1
        parts = [f"{v} {k}" for k, v in counts.items()]
        summary = "Validation issues: " + ", ".join(parts) + "."

    return ValidationReport(items=items, summary=summary)


def validate_serialized_xml(root: ET.Element) -> ValidationReport:
    """Check the final document, including opaque XML omitted by model checks.

    Supports both the current GUI-confirmed E shape and older twin-chain
    documents. Parser callers can continue accepting legacy flat MLT; this
    runtime shape gate is intended for documents about to be written; it is
    not a universal conformance checker for every Kdenlive 25 document.
    """
    items: list[ValidationItem] = []

    def error(element: ET.Element, message: str) -> None:
        items.append(ValidationItem(
            severity=ValidationSeverity.blocking_error,
            category="xml_structure", message=message,
            location=f"{element.tag}:{element.get('id', '')}",
        ))

    nodes: dict[str, ET.Element] = {}
    for element in root:
        identity = element.get("id")
        if identity:
            if identity in nodes:
                error(element, f"Duplicate XML id '{identity}'; assign a unique element id.")
            nodes[identity] = element
    props = {identity: xml_properties(element) for identity, element in nodes.items()}
    profile = root.find("profile")
    if profile is None:
        error(root, "Missing MLT profile.")
    else:
        for name in ("width", "height", "frame_rate_num", "frame_rate_den"):
            value = profile.get(name, "")
            if not value.isdigit() or int(value) <= 0:
                error(profile, f"Profile {name} must be a positive integer.")
    sequences = [element for element in root.findall("tractor")
                 if xml_properties(element).get("kdenlive:producer_type") == "17"]
    sequence_refs = {sequence.get("id", "") for sequence in sequences}
    if len(sequences) != 1:
        error(root, "Expected exactly one main sequence tractor (kdenlive:producer_type=17).")
    for element in root:
        properties = xml_properties(element)
        if "kdenlive:uuid" in properties and element not in sequences:
            error(element, "kdenlive:uuid belongs only on the main sequence tractor.")
    main_bin = nodes.get("main_bin")
    if main_bin is None or main_bin.tag != "playlist":
        error(root, "Missing main_bin playlist; register the sequence and media clips.")
        bin_refs: set[str] = set()
    else:
        bin_refs = {entry.get("producer", "") for entry in main_bin.findall("entry")}
        if xml_properties(main_bin).get("xml_retain") != "1":
            error(main_bin, "main_bin requires xml_retain=1 for bin registration.")
    timeline_refs = {entry.get("producer", "") for playlist in root.findall("playlist")
                     if playlist is not main_bin for entry in playlist.findall("entry")}
    registered_clip_ids = {
        props.get(reference, {}).get("kdenlive:id", "")
        for reference in bin_refs if reference not in sequence_refs
    }
    twin_shape = any(
        # Native bin clips may themselves use avformat-novalidate and be
        # preserved as opaque chains alongside regenerated E-shape media.
        # Only the explicit timeline/bin service roles identify our strict
        # twin contract; a bin-only native chain is not a timeline twin.
        (identity in timeline_refs and identity not in bin_refs
         and properties.get("mlt_service") == "avformat-novalidate")
        or (identity in bin_refs and element.tag == "chain"
            and properties.get("kdenlive:control_uuid")
            and properties.get("mlt_service") == "avformat")
        for identity, element in nodes.items() for properties in [props[identity]]
    )
    parents = {child: parent for parent in root.iter() for child in parent}
    for sequence in sequences:
        properties = xml_properties(sequence)
        sequence_uuid = properties.get("kdenlive:uuid")
        if not sequence_uuid or sequence_uuid != properties.get("kdenlive:control_uuid"):
            error(sequence, "Sequence uuid and control_uuid must be present and equal.")
        if sequence.get("id") not in bin_refs:
            error(sequence, "Main sequence must be registered in main_bin.")
        wrappers = [element for element in root.findall("tractor")
                    if xml_properties(element).get("kdenlive:projectTractor") == "1"]
        if not any(track.get("producer") == sequence.get("id")
                   for wrapper in wrappers for track in wrapper.findall("track")):
            error(sequence, "Project tractor must reference the main sequence.")
        for track in sequence.findall("track"):
            target = nodes.get(track.get("producer", ""))
            if target is not None and xml_properties(target).get("kdenlive:playlistid") == "black_track":
                if "hide" in track.attrib:
                    error(sequence, "Sequence background track must have no hide attribute.")
                continue
            if target is None or target.tag != "tractor":
                error(sequence, f"Sequence track '{track.get('producer')}' must reference a track tractor.")
                continue
            lanes = target.findall("track")
            if len(lanes) != 2 or any(nodes.get(lane.get("producer", "")) is None
                                     or nodes[lane.get("producer", "")].tag != "playlist"
                                     for lane in lanes):
                error(target, "Track tractor requires two existing playlist lanes.")
            if lanes and all(lane.get("hide") == "video" for lane in lanes):
                services = {xml_properties(f).get("mlt_service") for f in target.findall("filter")
                            if xml_properties(f).get("internal_added") == "237"}
                if not {"volume", "panner", "audiolevel"}.issubset(services):
                    error(target, "Audio track requires internal volume, panner, and audiolevel filters.")
    for element in root.iter():
        if element.tag not in {"entry", "track"}:
            continue
        reference = element.get("producer", "")
        producer = nodes.get(reference)
        if producer is None:
            error(element, f"Unknown producer reference '{reference}'.")
            continue
        if element.tag != "entry":
            continue
        properties = props[reference]
        # Native documents may use MLT timecodes. Only compare integer frame
        # values here; never mistake a timecode for an invalid frame count.
        out = element.get("out", "")
        length = properties.get("length", "")
        if out.isdigit() and length.isdigit() and int(out) >= int(length):
            error(element, f"Entry for '{reference}' ends at frame {out}, beyond length {length}; extend the producer length or shorten the entry.")
        for boundary in ("in", "out"):
            value = element.get(boundary, "")
            if value.startswith("-"):
                error(element, f"Entry {boundary} must not be negative.")
        start = element.get("in", "")
        if start.isdigit() and out.isdigit() and int(start) > int(out):
            error(element, "Entry in frame must not exceed its out frame.")
        parent = parents.get(element)
        timeline_entry = (parent is not None and parent.tag == "playlist"
                          and parent is not main_bin
                          and xml_properties(parent).get("kdenlive:playlistid") != "black_track")
        if timeline_entry and properties.get("kdenlive:id"):
            entry_clip_id = xml_properties(element).get("kdenlive:id", "")
            if entry_clip_id != properties["kdenlive:id"]:
                error(element, f"Timeline entry for '{reference}' must carry its bin clip's kdenlive:id ({properties['kdenlive:id']}).")
        if timeline_entry and producer.tag in {"producer", "chain"}:
            remap_variant = (
                properties.get("mlt_service") == "timewarp"
                or (producer.tag == "chain" and any(
                    child.tag == "link" and (
                        child.get("mlt_service") == "timeremap"
                        or xml_properties(child).get("mlt_service") == "timeremap"
                    ) for child in producer
                ))
            )
            shared_registered = (
                remap_variant
                and bool(properties.get("kdenlive:id"))
                and properties.get("kdenlive:id") in registered_clip_ids
            )
            if twin_shape:
                clip_id = properties.get("kdenlive:id")
                registered = reference in bin_refs or shared_registered or any(
                    props[bin_ref].get("kdenlive:id") == clip_id
                    and props[bin_ref].get("kdenlive:control_uuid") == properties.get("kdenlive:control_uuid")
                    for bin_ref in bin_refs if bin_ref in props
                )
            else:
                registered = reference in bin_refs or shared_registered
            if not registered:
                error(element, f"Timeline producer '{reference}' has no matching registered bin clip.")
    bin_ids: dict[str, str] = {}
    sequence_ids = {
        props.get(sequence.get("id", ""), {}).get("kdenlive:id", "")
        for sequence in sequences
    }
    folder_id = (
        xml_properties(main_bin).get("kdenlive:sequenceFolder", "")
        if main_bin is not None else ""
    )
    for reference in bin_refs:
        element = nodes.get(reference)
        if element is None or element.tag not in {"producer", "chain", "tractor"}:
            continue
        clip_id = props[reference].get("kdenlive:id", "")
        if reference not in sequence_refs:
            if clip_id in sequence_ids:
                error(element, f"Bin clip '{reference}' uses the main sequence kdenlive:id {clip_id}.")
            if folder_id and clip_id == folder_id:
                error(element, f"Bin clip '{reference}' uses kdenlive:id {folder_id}, which is the Sequences folder id; user clips start at 4.")
        if not clip_id.isdigit():
            error(element, "Bin clips require a positive integer kdenlive:id.")
        elif clip_id in bin_ids:
            error(element, f"Bin id {clip_id} is shared with '{bin_ids[clip_id]}'; assign unique clip ids.")
        elif int(clip_id) <= 0:
            error(element, "Bin clips require a positive integer kdenlive:id.")
        bin_ids[clip_id] = reference
    if main_bin is not None:
        for entry in main_bin.findall("entry"):
            reference = entry.get("producer", "")
            if reference in sequence_refs:
                continue
            producer_props = props.get(reference, {})
            out = entry.get("out", "")
            length = producer_props.get("length", "")
            if out.isdigit() and length.isdigit() and int(out) != int(length) - 1:
                error(entry, f"main_bin media entry for '{reference}' must end at length - 1 ({int(length) - 1}), got {out}.")
    if twin_shape:
        for identity, element in nodes.items():
            properties = props[identity]
            if properties.get("mlt_service") not in {"avformat", "avformat-novalidate"}:
                continue
            if not properties.get("kdenlive:control_uuid"):
                error(element, "AV twin chains require a nonempty kdenlive:control_uuid.")
            clip_id = properties.get("kdenlive:id", "")
            if not clip_id.isdigit() or int(clip_id) < 4:
                error(element, "Twin-shape user clip IDs must start at 4; 2 and 3 are reserved.")
            twins = [other for other_id, other in nodes.items() if other_id != identity
                     and other.tag == "chain"
                     and props[other_id].get("kdenlive:control_uuid") == properties.get("kdenlive:control_uuid")
                     and props[other_id].get("kdenlive:id") == properties.get("kdenlive:id")]
            expected_service = ("avformat-novalidate" if identity in bin_refs else "avformat")
            matching_twins = [other for other in twins
                              if props[other.get("id", "")].get("mlt_service") == expected_service
                              and ((other.get("id") in bin_refs) != (identity in bin_refs))]
            if element.tag != "chain" or len(matching_twins) != 1:
                error(element, "AV media requires one timeline avformat-novalidate chain and one registered bin avformat chain with shared control_uuid and clip id.")
            expected_own_service = "avformat" if identity in bin_refs else "avformat-novalidate"
            if properties.get("mlt_service") != expected_own_service:
                error(element, f"AV chain '{identity}' must use {expected_own_service} for its bin/timeline role.")
            if identity in bin_refs and properties.get("kdenlive:monitorPosition") != "0":
                error(element, "Bin twin requires kdenlive:monitorPosition=0.")
            if properties.get("kdenlive:kextractor") != "1":
                error(element, "Both AV twins require kdenlive:kextractor=1.")
            if identity in bin_refs:
                for entry in main_bin.findall("entry") if main_bin is not None else []:
                    if entry.get("producer") == identity:
                        length = properties.get("length", "")
                        out = entry.get("out", "")
                        if length.isdigit() and out.isdigit() and int(out) != int(length) - 1:
                            error(entry, f"Bin twin '{identity}' requires out=length-1.")
    return ValidationReport(items=items, summary=(
        f"Serialized XML has {len(items)} structural issue(s)." if items
        else "Serialized XML structure is valid."
    ))
