"""Kdenlive project patcher.

Applies a list of timeline intents to a KdenliveProject, returning a new
(not mutated) instance.
"""
from __future__ import annotations

import copy
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
    Track,
)
from workshop_video_brain.core.models.timeline import (
    AddClip,
    AddComposition,
    AddEffect,
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
        elif isinstance(intent, AddEffect):
            _apply_add_effect(new_project, intent)
        elif isinstance(intent, AddComposition):
            _apply_add_composition(new_project, intent)
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

    # Ensure the producer exists in the project.  Kdenlive needs at
    # minimum ``mlt_service`` and ``length`` to load the producer;
    # without them the bin clip is unloadable.  ``make_avformat_producer``
    # bakes in the full v25 property set verified against the KDE test
    # suite.  For color/title producers the caller should pre-populate
    # ``project.producers`` directly.
    existing_ids = {p.id for p in project.producers}
    if intent.producer_id and intent.producer_id not in existing_ids:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.producers import (
            make_avformat_producer,
        )
        clip_length = max(1, intent.out_point + 1)
        new_producer = make_avformat_producer(
            intent.producer_id,
            intent.source_path or "",
            length_frames=clip_length,
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
    """Set the playback speed of the clip at clip_index.

    Updates the playlist entry's ``speed`` field so the serializer emits a
    matching ``<producer mlt_service="timewarp">`` and rewrites the entry's
    producer reference to it.  Also rescales ``out_point`` so the entry's
    duration reflects the new playback speed (frames are at the
    timewarped rate).
    """
    if intent.speed <= 0:
        logger.warning(
            "SetClipSpeed: speed must be positive (got %.2f) – skipped.", intent.speed
        )
        return

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
    # Compute the timewarped duration: the entry covers fewer frames at the
    # new speed.  ``out`` is the index of the last frame, so the displayed
    # frame count is ``(out - in + 1) / speed``; the new last-frame index
    # is in_point + (count - 1).
    original_count = entry.out_point - entry.in_point + 1
    new_count = max(1, int(round(original_count / intent.speed)))
    entry.speed = intent.speed
    entry.out_point = entry.in_point + new_count - 1
    logger.info(
        "SetClipSpeed: clip %d in playlist '%s' set to speed=%.2f (was %d frames -> %d frames)",
        intent.clip_index, intent.track_ref, intent.speed,
        original_count, new_count,
    )


def _apply_audio_fade(project: KdenliveProject, intent: AudioFade) -> None:
    """Append an audio fade-in or fade-out filter to a clip's entry.

    Emits the v25 shape verified against ``audio-mix.kdenlive`` from the
    KDE test suite: a ``<filter>`` child inside the playlist ``<entry>``
    with ``mlt_service=volume``, ``kdenlive_id=fadein``/``fadeout``,
    scalar ``gain``/``end`` (NOT keyframe strings), and ``in``/``out``
    element attributes positioning the ramp window.

    The previous opaque-XML implementation was rejected by Kdenlive 25.x.
    """
    from workshop_video_brain.core.models.kdenlive import EntryFilter

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
    entry_count = entry.out_point - entry.in_point + 1
    duration = max(1, min(intent.duration_frames, entry_count))
    fade_type = intent.fade_type

    if fade_type == "in":
        gain, end = "0", "1"
        # fadein starts at entry-local frame 0 and runs for ``duration``
        # frames.  Reference omits the ``in`` attribute when fade starts
        # at clip start, but emitting it explicitly is harmless.
        in_frame = 0
        out_frame = duration - 1
    else:
        gain, end = "1", "0"
        # fadeout sits at the tail: starts ``duration`` frames before the
        # entry ends, ends at the last frame.
        in_frame = max(0, entry_count - duration)
        out_frame = entry_count - 1

    entry.filters.append(
        EntryFilter(
            id=f"audiofade_{fade_type}_{intent.track_ref}_{intent.clip_index}",
            in_frame=in_frame,
            out_frame=out_frame,
            properties={
                "window": "75",
                "max_gain": "20dB",
                "mlt_service": "volume",
                "kdenlive_id": f"fade{fade_type}",
                "gain": gain,
                "end": end,
                "kdenlive:collapsed": "0",
            },
        )
    )
    logger.info(
        "AudioFade: added fade%s (%d frames) for clip %d in playlist '%s'",
        fade_type, duration, intent.clip_index, intent.track_ref,
    )


def _apply_set_track_mute(project: KdenliveProject, intent: SetTrackMute) -> None:
    """Set ``Track.muted`` so the serializer emits ``hide="both"`` on the
    per-track tractor's sub-tracks (the v25 mute shape, verified against
    ``audio-mix.kdenlive`` from the KDE test suite)."""
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackMute: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    track.muted = bool(intent.muted)
    logger.info(
        "SetTrackMute: track '%s' muted=%s",
        intent.track_ref, intent.muted,
    )


def _apply_set_track_visibility(project: KdenliveProject, intent: SetTrackVisibility) -> None:
    """Set ``Track.hidden`` so the serializer emits ``hide="both"`` on the
    per-track tractor's sub-tracks for video tracks (mute equivalent)."""
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackVisibility: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    track.hidden = not bool(intent.visible)
    logger.info(
        "SetTrackVisibility: track '%s' visible=%s",
        intent.track_ref, intent.visible,
    )


def _apply_add_effect(project: KdenliveProject, intent: AddEffect) -> None:
    """Insert an MLT filter element for a clip on a track.

    NOTE: This emits the legacy opaque-XML form at document root because
    the existing ``effect_stack_*`` and ``effect_reorder`` MCP tooling
    operates on ``project.opaque_elements`` to manage filter ordering.
    Kdenlive 25.x ignores this XML shape (filters need to live inside
    the playlist ``<entry>`` element, not at root) -- see
    ``vault/wiki/kdenlive-test-suite-coverage-audit.md`` for the
    backlog of opaque-shaped tools that need rewiring.

    For new code that needs v25-correct effect filters, append directly
    to ``PlaylistEntry.filters`` with the right ``EntryFilter`` shape
    (see smoke 8 / 9).  Migrating the stack-ordering tools to operate
    on ``entry.filters`` lists is a follow-up.
    """
    # Resolve track by index
    if intent.track_index < 0 or intent.track_index >= len(project.playlists):
        logger.warning(
            "AddEffect: track_index %d out of range (have %d playlists) -- skipped.",
            intent.track_index, len(project.playlists),
        )
        return

    playlist = project.playlists[intent.track_index]
    real_entries = [e for e in playlist.entries if e.producer_id]

    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "AddEffect: clip_index %d out of range (playlist '%s' has %d clips) -- skipped.",
            intent.clip_index, playlist.id, len(real_entries),
        )
        return

    entry = real_entries[intent.clip_index]

    # Build filter XML (legacy opaque form -- see docstring note above).
    props_xml = "".join(
        f'<property name="{k}">{v}</property>' for k, v in intent.params.items()
    )
    filter_id = f"effect_{intent.track_index}_{intent.clip_index}_{intent.effect_name}"
    xml = (
        f'<filter id="{filter_id}" '
        f'mlt_service="{intent.effect_name}" '
        f'track="{intent.track_index}" '
        f'clip_index="{intent.clip_index}">'
        f'{props_xml}'
        f'</filter>'
    )

    element = OpaqueElement(
        tag="filter",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AddEffect: applied '%s' to clip %d on track '%s'",
        intent.effect_name, intent.clip_index, playlist.id,
    )


def _apply_add_composition(project: KdenliveProject, intent: AddComposition) -> None:
    """Insert an MLT transition element between two tracks.

    Builds a <transition mlt_service="..."> element with a_track, b_track,
    in, out properties plus any extra params, and appends it as an OpaqueElement.
    """
    # Build core properties
    props = {
        "a_track": str(intent.track_a),
        "b_track": str(intent.track_b),
        "in": str(intent.start_frame),
        "out": str(intent.end_frame),
    }
    # Merge extra params (extra params cannot override core keys)
    for k, v in intent.params.items():
        if k not in props:
            props[k] = v

    props_xml = "".join(
        f'<property name="{k}">{v}</property>' for k, v in props.items()
    )
    xml = (
        f'<transition mlt_service="{intent.composition_type}">'
        f'{props_xml}'
        f'</transition>'
    )

    element = OpaqueElement(
        tag="transition",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AddComposition: applied '%s' between tracks %d and %d (frames %d-%d)",
        intent.composition_type, intent.track_a, intent.track_b,
        intent.start_frame, intent.end_frame,
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


# ---------------------------------------------------------------------------
# Effect-property accessors (additive; used by the keyframe pipeline).
# ---------------------------------------------------------------------------


def _iter_clip_filters(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
) -> list[tuple[int, OpaqueElement, ET.Element]]:
    """Return [(effect_index, opaque_element, parsed_root), ...] for a clip.

    effect_index is the position of the filter within this clip's filter
    stack (0-based), NOT the index in project.opaque_elements. Stack order
    matches insertion order in project.opaque_elements.

    Raises IndexError if clip_ref refers to a non-existent track or clip.
    """
    track_index, clip_index = clip_ref

    if track_index < 0 or track_index >= len(project.playlists):
        raise IndexError(
            f"track_index {track_index} out of range "
            f"(have {len(project.playlists)} playlists)"
        )

    playlist = project.playlists[track_index]
    real_entries = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        raise IndexError(
            f"clip_index {clip_index} out of range "
            f"(track has {len(real_entries)} clips)"
        )

    result: list[tuple[int, OpaqueElement, ET.Element]] = []
    track_attr = str(track_index)
    clip_attr = str(clip_index)
    effect_index = 0
    for elem in project.opaque_elements:
        if elem.tag != "filter":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        if root.get("track") != track_attr or root.get("clip_index") != clip_attr:
            continue
        result.append((effect_index, elem, root))
        effect_index += 1
    return result


def list_effects(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
) -> list[dict]:
    """Enumerate filters on a clip in stack order.

    Each dict has keys: index, mlt_service, kdenlive_id, properties.
    """
    out: list[dict] = []
    for effect_index, _elem, root in _iter_clip_filters(project, clip_ref):
        properties: dict[str, str] = {}
        kdenlive_id = ""
        for child in root:
            if child.tag != "property":
                continue
            name = child.get("name")
            if name is None:
                continue
            text = child.text or ""
            properties[name] = text
            if name == "kdenlive_id":
                kdenlive_id = text
        out.append(
            {
                "index": effect_index,
                "mlt_service": root.get("mlt_service") or "",
                "kdenlive_id": kdenlive_id,
                "properties": properties,
            }
        )
    return out


def get_effect_property(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
    property_name: str,
) -> str | None:
    """Return the property value for a filter on a clip, or None if missing.

    Raises IndexError if effect_index is out of range for the clip's stack.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    _idx, _elem, root = filters[effect_index]
    for child in root:
        if child.tag == "property" and child.get("name") == property_name:
            return child.text or ""
    return None


def set_effect_property(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
    property_name: str,
    value: str,
) -> None:
    """Set (or create) a <property name=...> entry on a clip's filter.

    Mutates project.opaque_elements in place by re-serializing the target
    filter's XML. Raises IndexError on bad clip_ref or effect_index.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    _idx, elem, root = filters[effect_index]
    target = None
    for child in root:
        if child.tag == "property" and child.get("name") == property_name:
            target = child
            break
    if target is None:
        target = ET.SubElement(root, "property", {"name": property_name})
    target.text = value
    elem.xml_string = ET.tostring(root, encoding="unicode")
    logger.info(
        "set_effect_property: clip %s effect %d property '%s'",
        clip_ref, effect_index, property_name,
    )


def insert_effect_xml(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    xml_string: str,
    position: int,
) -> None:
    """Insert a new filter OpaqueElement into a clip's effect stack.

    `position` is a per-clip stack index in [0, len(stack)]. 0 inserts at
    the top of the stack; `len(stack)` appends to the bottom.

    Raises IndexError on bad clip_ref or out-of-range position.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if position < 0 or position > len(filters):
        raise IndexError(
            f"position {position} out of range "
            f"(clip has {len(filters)} filters)"
        )

    new_element = OpaqueElement(
        tag="filter",
        xml_string=xml_string,
        position_hint="after_tractor",
    )

    if len(filters) == 0:
        project.opaque_elements.append(new_element)
    elif position < len(filters):
        abs_index = project.opaque_elements.index(filters[position][1])
        project.opaque_elements.insert(abs_index, new_element)
    else:
        abs_index = project.opaque_elements.index(filters[-1][1]) + 1
        project.opaque_elements.insert(abs_index, new_element)

    logger.info(
        "insert_effect_xml: clip %s position %d (stack len now %d)",
        clip_ref, position, len(filters) + 1,
    )


def remove_effect(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
) -> None:
    """Remove the filter at stack-index `effect_index` from a clip.

    Raises IndexError on bad clip_ref or out-of-range effect_index.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    target_elem = filters[effect_index][1]
    project.opaque_elements.remove(target_elem)
    logger.info(
        "remove_effect: clip %s effect %d (stack len now %d)",
        clip_ref, effect_index, len(filters) - 1,
    )


def reorder_effects(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    from_index: int,
    to_index: int,
) -> None:
    """Move a filter within a clip's stack from `from_index` to `to_index`.

    Semantics mirror `list.insert(to, list.pop(from))` applied to the clip's
    filter subset. `from_index == to_index` is a silent no-op.

    Raises IndexError on bad clip_ref or out-of-range indices.
    """
    if from_index == to_index:
        return

    filters = _iter_clip_filters(project, clip_ref)
    if from_index < 0 or from_index >= len(filters):
        raise IndexError(
            f"from_index {from_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    if to_index < 0 or to_index >= len(filters):
        raise IndexError(
            f"to_index {to_index} out of range "
            f"(clip has {len(filters)} filters)"
        )

    moving = filters[from_index][1]
    project.opaque_elements.remove(moving)

    filters_after = _iter_clip_filters(project, clip_ref)
    if to_index < len(filters_after):
        abs_index = project.opaque_elements.index(filters_after[to_index][1])
    elif len(filters_after) > 0:
        abs_index = project.opaque_elements.index(filters_after[-1][1]) + 1
    else:
        abs_index = len(project.opaque_elements)

    project.opaque_elements.insert(abs_index, moving)
    logger.info(
        "reorder_effects: clip %s moved %d -> %d",
        clip_ref, from_index, to_index,
    )
