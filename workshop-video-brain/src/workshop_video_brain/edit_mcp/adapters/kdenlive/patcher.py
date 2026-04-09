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
from workshop_video_brain.core.models.timeline import (
    AddClip,
    AddGuide,
    AddSubtitleRegion,
    AddTransition,
    AudioFade,
    CreateTrack,
    InsertGap,
    MoveClip,
    RemoveClip,
    RippleDelete,
    SetClipSpeed,
    SetTrackMute,
    SetTrackVisibility,
    SplitClip,
    TrimClip,
)
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
    - AddTransition: applies a transition element
    - AddClip: inserts a clip into a playlist
    - TrimClip: adjusts in/out points on an existing clip entry
    - InsertGap: inserts a blank gap entry into a playlist
    - AddSubtitleRegion: adds a subtitle guide marker
    - CreateTrack: adds a new track and playlist
    - RemoveClip: removes a clip from a playlist by index
    - MoveClip: moves a clip within a playlist
    - SplitClip: splits a clip into two at a frame offset
    - RippleDelete: removes a clip, closing the gap
    - SetClipSpeed: adds a speed-change opaque element for a clip
    - AudioFade: adds an audio fade opaque element for a clip
    - SetTrackMute: mutes or unmutes a track via opaque element
    - SetTrackVisibility: shows or hides a track via opaque element

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
        elif isinstance(intent, TrimClip):
            _apply_trim_clip(new_project, intent)
        elif isinstance(intent, InsertGap):
            _apply_insert_gap(new_project, intent)
        elif isinstance(intent, AddSubtitleRegion):
            _apply_add_subtitle_region(new_project, intent)
        elif isinstance(intent, CreateTrack):
            _apply_create_track(new_project, intent)
        elif isinstance(intent, RemoveClip):
            _apply_remove_clip(new_project, intent)
        elif isinstance(intent, MoveClip):
            _apply_move_clip(new_project, intent)
        elif isinstance(intent, SplitClip):
            _apply_split_clip(new_project, intent)
        elif isinstance(intent, RippleDelete):
            _apply_ripple_delete(new_project, intent)
        elif isinstance(intent, SetClipSpeed):
            _apply_set_clip_speed(new_project, intent)
        elif isinstance(intent, AudioFade):
            _apply_audio_fade(new_project, intent)
        elif isinstance(intent, SetTrackMute):
            _apply_set_track_mute(new_project, intent)
        elif isinstance(intent, SetTrackVisibility):
            _apply_set_track_visibility(new_project, intent)
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


def _find_playlist(project: KdenliveProject, track_ref: str) -> Playlist | None:
    """Return the playlist with the given id, or None."""
    for playlist in project.playlists:
        if playlist.id == track_ref:
            return playlist
    return None


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
    target_playlist = _find_playlist(project, target_ref)

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


def _apply_trim_clip(project: KdenliveProject, intent: TrimClip) -> None:
    """Apply a TrimClip intent: update in/out points on a clip entry.

    clip_ref is interpreted as either a playlist_id:index pair (e.g. "pl_video:0")
    or a bare index into the first playlist.  new_in / new_out of -1 means
    "leave unchanged".
    """
    # Resolve clip_ref → playlist + index
    if ":" in intent.clip_ref:
        parts = intent.clip_ref.rsplit(":", 1)
        playlist_id = parts[0]
        try:
            clip_index = int(parts[1])
        except ValueError:
            logger.warning("TrimClip: invalid clip_ref format '%s' – skipped.", intent.clip_ref)
            return
        playlist = _find_playlist(project, playlist_id)
    else:
        # bare integer index into first non-empty playlist
        try:
            clip_index = int(intent.clip_ref)
        except ValueError:
            logger.warning("TrimClip: invalid clip_ref '%s' – skipped.", intent.clip_ref)
            return
        playlist = project.playlists[0] if project.playlists else None

    if playlist is None:
        logger.warning("TrimClip: playlist not found for clip_ref '%s' – skipped.", intent.clip_ref)
        return

    entries = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(entries):
        logger.warning(
            "TrimClip: clip_index %d out of range (playlist has %d clips) – skipped.",
            clip_index, len(entries),
        )
        return

    entry = entries[clip_index]
    if intent.new_in >= 0:
        entry.in_point = intent.new_in
    if intent.new_out >= 0:
        entry.out_point = intent.new_out
    logger.info(
        "TrimClip: clip %d in playlist '%s' → in=%d out=%d",
        clip_index, playlist.id, entry.in_point, entry.out_point,
    )


def _apply_insert_gap(project: KdenliveProject, intent: InsertGap) -> None:
    """Insert a blank PlaylistEntry at the given position in the target playlist."""
    target_ref = intent.track_id
    playlist = _find_playlist(project, target_ref)

    if playlist is None:
        logger.warning("InsertGap: no playlist found with id '%s' – skipped.", target_ref)
        return

    # A blank entry has producer_id="" and represents a gap
    gap_entry = PlaylistEntry(
        producer_id="",
        in_point=0,
        out_point=max(0, intent.duration_frames - 1),
    )
    pos = min(intent.position, len(playlist.entries))
    playlist.entries.insert(pos, gap_entry)
    logger.info(
        "InsertGap: inserted %d-frame gap at position %d in playlist '%s'",
        intent.duration_frames, pos, target_ref,
    )


def _apply_add_subtitle_region(project: KdenliveProject, intent: AddSubtitleRegion) -> None:
    """Add a subtitle region as a Guide with label 'SUBTITLE: {text}'."""
    fps = project.profile.fps or 25.0
    position_frames = int(intent.start_seconds * fps)
    guide = Guide(
        position=position_frames,
        label=f"SUBTITLE: {intent.text}",
    )
    project.guides.append(guide)
    logger.info(
        "AddSubtitleRegion: added guide at frame %d with text '%s'",
        position_frames, intent.text,
    )


def _apply_create_track(project: KdenliveProject, intent: CreateTrack) -> None:
    """Add a new Track and corresponding empty Playlist to the project."""
    # Generate a unique ID for the track
    existing_ids = {t.id for t in project.tracks} | {p.id for p in project.playlists}
    base = f"playlist_{intent.track_type}"
    track_id = base
    counter = 1
    while track_id in existing_ids:
        track_id = f"{base}_{counter}"
        counter += 1

    name = intent.name or f"{intent.track_type.capitalize()} {counter}"
    new_track = Track(id=track_id, track_type=intent.track_type, name=name)
    new_playlist = Playlist(id=track_id)

    project.tracks.append(new_track)
    project.playlists.append(new_playlist)
    logger.info(
        "CreateTrack: added %s track '%s' with playlist '%s'",
        intent.track_type, name, track_id,
    )


def _apply_remove_clip(project: KdenliveProject, intent: RemoveClip) -> None:
    """Remove the entry at clip_index from the target playlist."""
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning("RemoveClip: no playlist found with id '%s' – skipped.", intent.track_ref)
        return

    # Work with real (non-blank) entries only for indexing
    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "RemoveClip: clip_index %d out of range (playlist has %d clips) – skipped.",
            intent.clip_index, len(real_entries),
        )
        return

    target_entry = real_entries[intent.clip_index]
    playlist.entries.remove(target_entry)
    logger.info(
        "RemoveClip: removed clip at index %d from playlist '%s'",
        intent.clip_index, intent.track_ref,
    )


def _apply_move_clip(project: KdenliveProject, intent: MoveClip) -> None:
    """Remove entry at from_index, insert at to_index in the same playlist."""
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning("MoveClip: no playlist found with id '%s' – skipped.", intent.track_ref)
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    n = len(real_entries)
    if intent.from_index < 0 or intent.from_index >= n:
        logger.warning(
            "MoveClip: from_index %d out of range (playlist has %d clips) – skipped.",
            intent.from_index, n,
        )
        return
    if intent.to_index < 0 or intent.to_index >= n:
        logger.warning(
            "MoveClip: to_index %d out of range (playlist has %d clips) – skipped.",
            intent.to_index, n,
        )
        return

    if intent.from_index == intent.to_index:
        return  # no-op

    # Operate on the full entries list (which may include blanks)
    # Find the actual object in the full list
    target_entry = real_entries[intent.from_index]
    full_idx = playlist.entries.index(target_entry)
    playlist.entries.pop(full_idx)

    # After removal, find insert position based on real-entry ordering
    # Rebuild real-entries list post-removal and find position
    dest_real_index = intent.to_index
    if intent.to_index > intent.from_index:
        dest_real_index -= 1  # shift because we removed one before

    remaining_real = [e for e in playlist.entries if e.producer_id]
    if dest_real_index >= len(remaining_real):
        # Insert at end
        playlist.entries.append(target_entry)
    else:
        dest_entry = remaining_real[dest_real_index]
        insert_at = playlist.entries.index(dest_entry)
        if intent.to_index > intent.from_index:
            insert_at += 1  # insert after the destination
        playlist.entries.insert(insert_at, target_entry)

    logger.info(
        "MoveClip: moved clip from index %d to %d in playlist '%s'",
        intent.from_index, intent.to_index, intent.track_ref,
    )


def _apply_split_clip(project: KdenliveProject, intent: SplitClip) -> None:
    """Split a clip at split_at_frame (offset within the clip), creating two entries."""
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning("SplitClip: no playlist found with id '%s' – skipped.", intent.track_ref)
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "SplitClip: clip_index %d out of range (playlist has %d clips) – skipped.",
            intent.clip_index, len(real_entries),
        )
        return

    entry = real_entries[intent.clip_index]
    clip_duration = entry.out_point - entry.in_point
    split_offset = intent.split_at_frame

    # Clamp split point within valid range
    split_offset = max(1, min(split_offset, clip_duration - 1))

    absolute_split = entry.in_point + split_offset

    first_entry = PlaylistEntry(
        producer_id=entry.producer_id,
        in_point=entry.in_point,
        out_point=absolute_split - 1,
    )
    second_entry = PlaylistEntry(
        producer_id=entry.producer_id,
        in_point=absolute_split,
        out_point=entry.out_point,
    )

    full_idx = playlist.entries.index(entry)
    playlist.entries[full_idx] = first_entry
    playlist.entries.insert(full_idx + 1, second_entry)

    logger.info(
        "SplitClip: split clip at index %d in playlist '%s' at frame %d",
        intent.clip_index, intent.track_ref, absolute_split,
    )


def _apply_ripple_delete(project: KdenliveProject, intent: RippleDelete) -> None:
    """Remove the entry at clip_index from the playlist.

    In a playlist-based Kdenlive project, removing an entry naturally closes
    the gap because subsequent entries shift left automatically.  There is no
    separate 'close gap' step needed.
    """
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning(
            "RippleDelete: no playlist found with id '%s' – skipped.", intent.track_ref
        )
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "RippleDelete: clip_index %d out of range (playlist has %d clips) – skipped.",
            intent.clip_index, len(real_entries),
        )
        return

    target_entry = real_entries[intent.clip_index]
    playlist.entries.remove(target_entry)
    logger.info(
        "RippleDelete: removed clip at index %d from playlist '%s' (gap closed)",
        intent.clip_index, intent.track_ref,
    )


def _apply_set_clip_speed(project: KdenliveProject, intent: SetClipSpeed) -> None:
    """Add a speed-change opaque element for the clip at clip_index."""
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning(
            "SetClipSpeed: no playlist found with id '%s' – skipped.", intent.track_ref
        )
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "SetClipSpeed: clip_index %d out of range – skipped.", intent.clip_index
        )
        return

    entry = real_entries[intent.clip_index]
    xml = (
        f'<filter id="speed_{intent.track_ref}_{intent.clip_index}" '
        f'type="speed" '
        f'producer="{entry.producer_id}" '
        f'track="{intent.track_ref}" '
        f'clip_index="{intent.clip_index}">'
        f'<property name="speed">{intent.speed}</property>'
        f'</filter>'
    )
    element = OpaqueElement(
        tag="filter",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "SetClipSpeed: added speed=%.2f filter for clip %d in playlist '%s'",
        intent.speed, intent.clip_index, intent.track_ref,
    )


def _apply_audio_fade(project: KdenliveProject, intent: AudioFade) -> None:
    """Add a volume-ramp filter for audio fade in/out."""
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning(
            "AudioFade: no playlist found with id '%s' – skipped.", intent.track_ref
        )
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "AudioFade: clip_index %d out of range – skipped.", intent.clip_index
        )
        return

    entry = real_entries[intent.clip_index]
    fade_type = intent.fade_type

    if fade_type == "in":
        # Volume ramps from 0 → 1 over duration_frames
        from_level = "0"
        to_level = "1"
    else:
        # Volume ramps from 1 → 0 over duration_frames
        from_level = "1"
        to_level = "0"

    xml = (
        f'<filter id="audiofade_{fade_type}_{intent.track_ref}_{intent.clip_index}" '
        f'type="volume" '
        f'producer="{entry.producer_id}" '
        f'track="{intent.track_ref}" '
        f'clip_index="{intent.clip_index}">'
        f'<property name="level">{from_level}=0;{to_level}={intent.duration_frames}</property>'
        f'<property name="kdenlive:fade_type">{fade_type}</property>'
        f'</filter>'
    )
    element = OpaqueElement(
        tag="filter",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AudioFade: added audio fade-%s (%d frames) for clip %d in playlist '%s'",
        fade_type, intent.duration_frames, intent.clip_index, intent.track_ref,
    )


def _apply_set_track_mute(project: KdenliveProject, intent: SetTrackMute) -> None:
    """Add a mute property element for the track."""
    # Verify track exists
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackMute: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    mute_value = "1" if intent.muted else "0"
    xml = (
        f'<property name="kdenlive:audio_mute" track="{intent.track_ref}">'
        f'{mute_value}'
        f'</property>'
    )
    element = OpaqueElement(
        tag="property",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "SetTrackMute: track '%s' muted=%s",
        intent.track_ref, intent.muted,
    )


def _apply_set_track_visibility(project: KdenliveProject, intent: SetTrackVisibility) -> None:
    """Add a visibility property element for the track."""
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackVisibility: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    if intent.visible:
        # Remove the hide=video property (store as empty value to signal removal)
        xml = (
            f'<property name="hide" track="{intent.track_ref}"></property>'
        )
    else:
        xml = (
            f'<property name="hide" track="{intent.track_ref}">video</property>'
        )
    element = OpaqueElement(
        tag="property",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "SetTrackVisibility: track '%s' visible=%s",
        intent.track_ref, intent.visible,
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
