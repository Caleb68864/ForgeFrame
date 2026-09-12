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
from collections.abc import Iterable, Iterator
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.validation import ValidationItem, ValidationReport
from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    FILE_BACKED_SERVICES,
    resolve_missing,
)

from .serializer import looks_like_media_resource

logger = logging.getLogger(__name__)

# Sane upper bound for guide positions (10 hours at 25 fps = 9_000_000 frames)
_MAX_GUIDE_FRAMES = 9_000_000


def _producer_services(project: KdenliveProject) -> Iterator[tuple[str, str, str]]:
    """Yield ``(producer_id, mlt_service, resource)`` as the file will be written.

    An in-memory producer may carry only a ``resource``: the serializer defaults
    such a producer to ``mlt_service=avformat`` when the resource looks like a
    path (``serializer.looks_like_media_resource``). Applying that default here is
    what keeps this check honest about the project that will actually be
    rendered -- without it the allowlist would silently skip every producer this
    repo builds and hands straight to ``serialize_project``.
    """
    for producer in project.producers:
        service = (producer.properties.get("mlt_service") or "").strip()
        if not service and looks_like_media_resource(producer.resource):
            service = "avformat"
        yield producer.id, service, producer.resource


def _media_items(
    triples: Iterable[tuple[str, str, str]], base: Path
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

    for miss in resolve_missing(triples, base):
        # Both the resource as written and where it resolved to: for a relative
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
                location=f"producer:{miss.producer_id}",
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
    3. Media paths exist on disk (when workspace_root is provided).
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
        items.extend(_media_items(_producer_services(project), base))

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
