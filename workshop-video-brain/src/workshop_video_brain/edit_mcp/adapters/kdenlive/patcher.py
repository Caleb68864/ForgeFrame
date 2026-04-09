"""Kdenlive project patcher.

Applies a list of timeline intents to a KdenliveProject, returning a new
(not mutated) instance.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip, AddGuide, AddTransition
from workshop_video_brain.core.models.transitions import (
    TransitionInstruction,
    TransitionPreset,
    TransitionType,
)

logger = logging.getLogger(__name__)


def calculate_crossfade(
    left_out: int,
    right_in: int,
    preset: TransitionPreset = TransitionPreset.medium,
) -> TransitionInstruction:
    """Calculate a crossfade transition between two clips.

    Args:
        left_out: Out-point (frame number) of the left clip.
        right_in: In-point (frame number) of the right clip.
        preset: Duration preset (short=12, medium=24, long=48 frames).

    Returns:
        TransitionInstruction with calculated duration and reason.

    If the clips are not adjacent or there is insufficient overlap, the
    duration is reduced to fit (minimum 1 frame). The reason field explains
    the decision made.
    """
    requested_frames = preset.frames
    # Calculate available overlap: how many frames the clips share
    overlap = left_out - right_in

    if overlap <= 0:
        # Clips are not overlapping — clips are adjacent or gapped
        if overlap < 0:
            reason = (
                f"Clips have a gap of {abs(overlap)} frames; "
                "crossfade uses minimum 1 frame."
            )
        else:
            reason = (
                "Clips are adjacent (no overlap); "
                "crossfade uses minimum 1 frame."
            )
        actual_frames = 1
    elif overlap < requested_frames:
        reason = (
            f"Insufficient overlap for {preset.value} preset "
            f"({requested_frames} frames requested, {overlap} available). "
            f"Falling back to {overlap} frames."
        )
        actual_frames = overlap
    else:
        reason = (
            f"Crossfade: {preset.value} preset ({requested_frames} frames). "
            f"Overlap available: {overlap} frames."
        )
        actual_frames = requested_frames

    return TransitionInstruction(
        type=TransitionType.crossfade,
        track_ref="",
        left_clip_ref="",
        right_clip_ref="",
        duration_frames=actual_frames,
        audio_link_behavior="linked",
        reason=reason,
    )


def patch_project(
    project: KdenliveProject,
    intents: list,
    workspace_root: Path | None = None,
    project_path: Path | None = None,
) -> KdenliveProject:
    """Apply *intents* to *project*, returning a new KdenliveProject.

    The input project is never mutated.  Supported intent types:
    - AddGuide: adds a Guide to the project
    - AddTransition: applies a transition element; snapshots project first
    - AddClip:  stub – logs a warning (full implementation deferred)

    Args:
        project: Source KdenliveProject (never mutated).
        intents: List of timeline intent objects.
        workspace_root: Optional workspace root for snapshotting before
                        AddTransition intents.
        project_path: Optional path to project file for snapshotting.
    """
    # Deep-copy so we never mutate the input
    new_project = project.model_copy(deep=True)
    _snapshot_taken = False

    for intent in intents:
        if isinstance(intent, AddGuide):
            _apply_add_guide(new_project, intent)
        elif isinstance(intent, AddClip):
            _apply_add_clip(new_project, intent)
        elif isinstance(intent, AddTransition):
            # Take a snapshot before applying the first transition
            if not _snapshot_taken and workspace_root and project_path:
                _take_snapshot(workspace_root, project_path)
                _snapshot_taken = True
            _apply_add_transition(new_project, intent)
        else:
            logger.warning(
                "patch_project: unsupported intent type %s – skipped",
                type(intent).__name__,
            )

    return new_project


def _take_snapshot(workspace_root: Path, project_path: Path) -> None:
    """Create a snapshot of *project_path* before applying destructive changes."""
    try:
        from workshop_video_brain.workspace import snapshot
        snapshot.create(
            workspace_root=workspace_root,
            file_to_snapshot=project_path,
            description="Pre-transition snapshot",
        )
        logger.info("Snapshot created before applying transition to %s", project_path)
    except Exception as exc:
        logger.warning("Could not create pre-transition snapshot: %s", exc)


def _apply_add_guide(project: KdenliveProject, intent: AddGuide) -> None:
    guide = Guide(
        position=intent.position_frames,
        label=intent.label,
        category=intent.category,
        comment=intent.comment,
    )
    project.guides.append(guide)


def _apply_add_clip(project: KdenliveProject, intent: AddClip) -> None:
    """Apply an AddClip intent: find playlist, ensure producer exists, insert entry."""
    # Resolve which playlist to target: prefer track_ref, fall back to track_id
    target_ref = intent.track_ref or intent.track_id

    # Find the matching playlist
    target_playlist: Playlist | None = None
    for playlist in project.playlists:
        if playlist.id == target_ref:
            target_playlist = playlist
            break

    if target_playlist is None:
        logger.warning(
            "AddClip: no playlist found with id '%s' – skipped.",
            target_ref,
        )
        return

    # Ensure the producer exists in the project
    existing_ids = {p.id for p in project.producers}
    if intent.producer_id and intent.producer_id not in existing_ids:
        new_producer = Producer(
            id=intent.producer_id,
            resource=intent.source_path or "",
            properties={"resource": intent.source_path} if intent.source_path else {},
        )
        project.producers.append(new_producer)
        logger.info(
            "AddClip: created new producer '%s' with resource '%s'",
            intent.producer_id,
            intent.source_path,
        )

    # Create the new playlist entry
    entry = PlaylistEntry(
        producer_id=intent.producer_id,
        in_point=intent.in_point,
        out_point=intent.out_point,
    )

    # Insert at the correct position
    if intent.position is None or intent.position < 0:
        target_playlist.entries.append(entry)
        logger.info(
            "AddClip: appended producer '%s' to playlist '%s'",
            intent.producer_id,
            target_ref,
        )
    else:
        pos = min(intent.position, len(target_playlist.entries))
        target_playlist.entries.insert(pos, entry)
        logger.info(
            "AddClip: inserted producer '%s' at position %d in playlist '%s'",
            intent.producer_id,
            pos,
            target_ref,
        )


def _apply_add_transition(project: KdenliveProject, intent: AddTransition) -> None:
    """Apply an AddTransition intent by appending a transition XML element.

    The transition is represented as an OpaqueElement so that the serializer
    can round-trip it verbatim.  The XML follows the MLT/Kdenlive convention
    for a mix (dissolve/crossfade) transition.
    """
    t_type = intent.type or "luma"
    track = intent.track_ref or "0"
    left_ref = intent.left_clip_ref or ""
    right_ref = intent.right_clip_ref or ""
    duration = intent.duration_frames

    # Build a minimal MLT transition XML element
    xml = (
        f'<transition id="transition_{len(project.opaque_elements)}" '
        f'type="{t_type}" '
        f'track="{track}" '
        f'left="{left_ref}" '
        f'right="{right_ref}" '
        f'duration="{duration}" />'
    )

    element = OpaqueElement(
        tag="transition",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "Applied %s transition on track '%s' (%d frames)",
        t_type,
        track,
        duration,
    )
