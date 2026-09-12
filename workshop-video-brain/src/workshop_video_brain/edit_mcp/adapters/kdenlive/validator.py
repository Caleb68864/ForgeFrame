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
