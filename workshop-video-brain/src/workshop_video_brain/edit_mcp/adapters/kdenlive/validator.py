"""Kdenlive project validator.

Runs structural and content checks on a KdenliveProject and returns a
ValidationReport with severity-labelled items.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.validation import ValidationItem, ValidationReport
from workshop_video_brain.core.models.enums import ValidationSeverity

logger = logging.getLogger(__name__)

# Sane upper bound for guide positions (10 hours at 25 fps = 9_000_000 frames)
_MAX_GUIDE_FRAMES = 9_000_000


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

    # --- 3. Media paths ---
    if workspace_root is not None:
        for producer in project.producers:
            resource = producer.resource
            if not resource:
                items.append(
                    ValidationItem(
                        severity=ValidationSeverity.warning,
                        category="media",
                        message=f"Producer '{producer.id}' has no resource path.",
                        location=f"producer:{producer.id}",
                    )
                )
                continue
            resource_path = Path(resource)
            # Resolve relative paths against workspace_root
            if not resource_path.is_absolute():
                resource_path = workspace_root / resource_path
            if not resource_path.exists():
                items.append(
                    ValidationItem(
                        severity=ValidationSeverity.error,
                        category="media",
                        message=f"Media file not found: {resource}",
                        location=f"producer:{producer.id}",
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
