"""Kdenlive project patcher -- timeline intent handlers.

Applies a list of timeline intents to a KdenliveProject, returning a new
(not mutated) instance. Contains ``patch_project`` and every ``_apply_*``
intent handler plus their private helpers (clips, transitions, speed/ramp,
fades, guides, track filters, the placement engine, hide directives...).

Split out of the original monolithic ``patcher.py`` (pure code movement, no
behaviour change); the public API remains importable from ``patcher`` via a
compatibility shim.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames
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
    AddTrackFilter,
    AddTransition,
    AudioFade,
    ClearTrackFilters,
    CreateTrack,
    InsertGap,
    MoveClip,
    MoveClipToTrack,
    PlaceClip,
    RemoveClip,
    RippleDelete,
    SetClipSpeed,
    SetTrackMute,
    SetTrackVisibility,
    SpeedRamp,
    SplitClip,
    TrimClip,
)
from workshop_video_brain.core.models.transitions import (
    TransitionInstruction,
    TransitionPreset,
    TransitionType,
)

logger = logging.getLogger(__name__)

__all__ = [
    "calculate_crossfade",
    "patch_project",
    "PatchReport",
]


@dataclass
class PatchReport:
    """Outcome of a :func:`patch_project` run.

    ``applied`` and ``skipped`` list the intents that took effect vs. those
    the patcher log-and-skipped (bad refs, out-of-range indices, invalid
    params...).  Each skipped entry records ``{"intent": <type name>,
    "reason": <the patcher's own skip message>}`` so a tool can surface the
    no-op instead of silently reporting success.
    """

    applied: list[str] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    @property
    def all_skipped(self) -> bool:
        """True when at least one intent ran and every one was skipped."""
        return bool(self.skipped) and not self.applied


class _SkipCapture(logging.Handler):
    """Collects this module's WARNING messages during a patch_project run.

    Skips are reported by the individual ``_apply_*`` handlers as warnings
    ending in ``skipped`` (an established convention); capturing them here lets
    :func:`patch_project` build a :class:`PatchReport` without touching the ~30
    handler signatures.  Applied-with-warning cases (e.g. a transition falling
    back to standalone emission) deliberately omit the word "skip" and so are
    not counted as skips.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:  # pragma: no cover - never let logging break a patch
            self.messages.append(str(record.msg))


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
    with_report: bool = False,
) -> KdenliveProject | tuple[KdenliveProject, PatchReport]:
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
        with_report: When True, return ``(project, PatchReport)`` instead of
            just the project.  Defaults to False so all existing callers keep
            their single-value return.
    """
    # Deep-copy so we never mutate the input
    new_project = project.model_copy(deep=True)
    _snapshot_taken = False

    report = PatchReport()
    capture = _SkipCapture()
    logger.addHandler(capture)
    try:
      for intent in intents:
        _msg_before = len(capture.messages)
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
        elif isinstance(intent, PlaceClip):
            _apply_place_clip(new_project, intent)
        elif isinstance(intent, MoveClipToTrack):
            _apply_move_clip_to_track(new_project, intent)
        elif isinstance(intent, SplitClip):
            _apply_split_clip(new_project, intent)
        elif isinstance(intent, RippleDelete):
            _apply_ripple_delete(new_project, intent)
        elif isinstance(intent, SetClipSpeed):
            _apply_set_clip_speed(new_project, intent)
        elif isinstance(intent, SpeedRamp):
            _apply_speed_ramp(new_project, intent)
        elif isinstance(intent, AudioFade):
            _apply_audio_fade(new_project, intent)
        elif isinstance(intent, SetTrackMute):
            _apply_set_track_mute(new_project, intent)
        elif isinstance(intent, SetTrackVisibility):
            _apply_set_track_visibility(new_project, intent)
        elif isinstance(intent, AddEffect):
            _apply_add_effect(new_project, intent)
        elif isinstance(intent, ClearTrackFilters):
            _apply_clear_track_filters(new_project, intent)
        elif isinstance(intent, AddTrackFilter):
            _apply_add_track_filter(new_project, intent)
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

        # Classify this intent: any new "skipped" warning => a no-op skip.
        new_msgs = capture.messages[_msg_before:]
        skip_msgs = [m for m in new_msgs if "skip" in m.lower()]
        if skip_msgs:
            report.skipped.append({
                "intent": type(intent).__name__,
                "reason": "; ".join(skip_msgs),
            })
        else:
            report.applied.append(type(intent).__name__)
    finally:
        logger.removeHandler(capture)

    if with_report:
        return new_project, report
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


def _playlist_index(project: KdenliveProject, track_ref: str) -> int | None:
    """Return the index of the playlist with the given id, or None.

    This index is the ``track`` value the effect-stack and serializer use to
    associate a clip filter with its <entry> (index into project.playlists).
    """
    for i, playlist in enumerate(project.playlists):
        if playlist.id == track_ref:
            return i
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
    position_frames = seconds_to_frames(intent.start_seconds, fps)
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


def _sync_tractor_out(project: KdenliveProject) -> None:
    """Keep the tractor ``out`` in step with the longest content playlist."""
    if project.tractor is None:
        return
    max_len = 0
    for pl in project.playlists:
        total = sum((e.out_point - e.in_point + 1) for e in pl.entries)
        max_len = max(max_len, total)
    if max_len > 0:
        project.tractor["out"] = str(max_len - 1)


def _remap_clip_filters(
    project: KdenliveProject,
    track_index: int,
    index_map: dict,
) -> None:
    """Shift/drop clip-filter ``clip_index`` associations after a placement.

    Clip effects are ``<filter>`` OpaqueElements keyed by ``track``/``clip_index``
    (index into the track's real clips).  Placement renumbers those clips, so we
    rewrite each affected filter's ``clip_index`` per ``index_map`` (old -> new),
    dropping filters whose clip was overwritten (mapped to ``None``).
    """
    track_attr = str(track_index)
    survivors: list[OpaqueElement] = []
    for elem in project.opaque_elements:
        if elem.tag != "filter":
            survivors.append(elem)
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            survivors.append(elem)
            continue
        if root.get("track") != track_attr or root.get("clip_index") is None:
            survivors.append(elem)
            continue
        try:
            old_ci = int(root.get("clip_index"))
        except (TypeError, ValueError):
            survivors.append(elem)
            continue
        new_ci = index_map.get(old_ci, old_ci)
        if new_ci is None:
            continue  # clip overwritten -> drop its filter
        if new_ci != old_ci:
            root.set("clip_index", str(new_ci))
            elem.xml_string = ET.tostring(root, encoding="unicode")
        survivors.append(elem)
    project.opaque_elements = survivors


def _apply_place_clip(project: KdenliveProject, intent: PlaceClip) -> None:
    """Place a clip at an absolute frame on a track (overwrite or insert)."""
    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp

    playlist = _find_playlist(project, intent.track_ref)
    track_index = _playlist_index(project, intent.track_ref)
    if playlist is None or track_index is None:
        logger.warning(
            "PlaceClip: no playlist found with id '%s' – skipped.", intent.track_ref
        )
        return
    if intent.out_point < intent.in_point:
        logger.warning("PlaceClip: out_point < in_point – skipped.")
        return

    # Register the producer if it isn't already present.
    if intent.producer_id and intent.producer_id not in {p.id for p in project.producers}:
        project.producers.append(
            Producer(
                id=intent.producer_id,
                resource=intent.source_path or "",
                properties={"resource": intent.source_path} if intent.source_path else {},
            )
        )

    clip = cp.PlacedClip(
        producer_id=intent.producer_id,
        in_point=intent.in_point,
        out_point=intent.out_point,
    )
    mode = (intent.mode or "overwrite").lower()
    if mode == "insert":
        result = cp.plan_insert(playlist.entries, intent.at_frame, clip)
    else:
        result = cp.plan_overwrite(playlist.entries, intent.at_frame, clip)

    playlist.entries = result.entries
    _remap_clip_filters(project, track_index, result.index_map)

    # Optional cross-track ripple: shift every other track + guides right by L.
    if mode == "insert" and intent.ripple_all_tracks:
        length = clip.length
        for other_index, other in enumerate(project.playlists):
            if other_index == track_index:
                continue
            other.entries = cp.plan_insert_blank(other.entries, intent.at_frame, length)
        for guide in project.guides:
            if guide.position >= intent.at_frame:
                guide.position += length

    _sync_tractor_out(project)
    logger.info(
        "PlaceClip: %s producer '%s' at frame %d on '%s' (new index %d)",
        mode, intent.producer_id, intent.at_frame, intent.track_ref, result.placed_index,
    )


def _apply_move_clip_to_track(project: KdenliveProject, intent: MoveClipToTrack) -> None:
    """Cross-track move: remove a clip from one track and place it on another."""
    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp

    src = _find_playlist(project, intent.from_track_ref)
    src_index = _playlist_index(project, intent.from_track_ref)
    dst = _find_playlist(project, intent.to_track_ref)
    dst_index = _playlist_index(project, intent.to_track_ref)
    if src is None or src_index is None:
        logger.warning(
            "MoveClipToTrack: source track '%s' not found – skipped.",
            intent.from_track_ref,
        )
        return
    if dst is None or dst_index is None:
        logger.warning(
            "MoveClipToTrack: target track '%s' not found – skipped.",
            intent.to_track_ref,
        )
        return

    try:
        moving = cp.clip_at_index(src.entries, intent.clip_index)
        orig_start = cp.clip_start_frame(src.entries, intent.clip_index)
    except IndexError as exc:
        logger.warning("MoveClipToTrack: %s – skipped.", exc)
        return

    producer_id = moving.producer_id
    in_point = moving.in_point
    out_point = moving.out_point
    length = cp.entry_length(moving)

    # Remove from the source: close the gap, or leave a same-length blank so the
    # rest of the source track keeps its timeline position.
    full_idx = src.entries.index(moving)
    if intent.close_gap:
        src.entries.pop(full_idx)
        # every real clip after the removed one drops by one index
        src_map = {}
        removed = intent.clip_index
        src_real = sum(1 for e in src.entries if e.producer_id) + 1
        for old in range(src_real):
            if old < removed:
                src_map[old] = old
            elif old == removed:
                src_map[old] = None
            else:
                src_map[old] = old - 1
        _remap_clip_filters(project, src_index, src_map)
    else:
        src.entries[full_idx] = PlaylistEntry(
            producer_id="", in_point=0, out_point=length - 1
        )
        # the moved clip's own filters no longer have a clip to attach to
        src_map = {intent.clip_index: None}
        _remap_clip_filters(project, src_index, src_map)

    at_frame = orig_start if intent.at_frame < 0 else intent.at_frame
    clip = cp.PlacedClip(producer_id=producer_id, in_point=in_point, out_point=out_point)
    mode = (intent.mode or "overwrite").lower()
    if mode == "insert":
        result = cp.plan_insert(dst.entries, at_frame, clip)
    else:
        result = cp.plan_overwrite(dst.entries, at_frame, clip)
    dst.entries = result.entries
    _remap_clip_filters(project, dst_index, result.index_map)

    _sync_tractor_out(project)
    logger.info(
        "MoveClipToTrack: clip %d '%s' -> track '%s' at frame %d (%s, close_gap=%s)",
        intent.clip_index, intent.from_track_ref, intent.to_track_ref,
        at_frame, mode, intent.close_gap,
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


def _timewarp_resource(producer: Producer, speed: float) -> str:
    """Build the MLT ``timewarp`` producer resource ``speed:<inner url>``.

    A color producer's inner URL is ``color:<value>``; a file-backed producer's
    is simply its resource path.  MLT's timewarp producer plays the wrapped
    producer at ``speed`` (2.0 = double speed / half duration).
    """
    resource = producer.resource or producer.properties.get("resource", "")
    service = producer.properties.get("mlt_service", "")
    if service and ":" not in resource and "/" not in resource and "." not in resource:
        inner = f"{service}:{resource}"
    else:
        inner = resource
    speed_str = f"{speed:g}"
    return f"{speed_str}:{inner}"


def _apply_set_clip_speed(project: KdenliveProject, intent: SetClipSpeed) -> None:
    """Change a clip's playback speed via an MLT ``timewarp`` producer swap.

    The old ``<filter type="speed">`` was a no-op in MLT (§1.1); real speed
    changes require wrapping the source in a ``timewarp:`` producer and scaling
    the entry's in/out so the timeline duration reflects the new speed.  Any
    linked entries (same producer at the same clip index on other tracks, e.g.
    the paired audio) are swapped too so the timeline stays in sync.
    """
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

    if intent.speed <= 0:
        logger.warning("SetClipSpeed: speed must be > 0 – skipped.")
        return

    entry = real_entries[intent.clip_index]
    source = next((p for p in project.producers if p.id == entry.producer_id), None)
    if source is None:
        logger.warning(
            "SetClipSpeed: producer '%s' not found – skipped.", entry.producer_id
        )
        return

    tw_id = f"{entry.producer_id}_tw{intent.speed:g}"
    if not any(p.id == tw_id for p in project.producers):
        tw_resource = _timewarp_resource(source, intent.speed)
        props = {
            "mlt_service": "timewarp",
            "resource": tw_resource,
            "warp_speed": f"{intent.speed:g}",
            "warp_resource": source.resource
            or source.properties.get("resource", ""),
        }
        if "length" in source.properties:
            try:
                src_len = int(source.properties["length"])
                props["length"] = str(max(1, round(src_len / intent.speed)))
            except ValueError:
                pass
        project.producers.append(
            Producer(id=tw_id, resource=tw_resource, properties=props)
        )

    def _rescale(e: PlaylistEntry) -> None:
        new_in = int(round(e.in_point / intent.speed))
        duration = e.out_point - e.in_point + 1
        new_len = max(1, int(round(duration / intent.speed)))
        e.producer_id = tw_id
        e.in_point = new_in
        e.out_point = new_in + new_len - 1

    # Swap the target entry and any linked copies (same original producer at the
    # same real-clip index on other playlists, e.g. the paired audio track).
    orig_producer = entry.producer_id
    _rescale(entry)
    for other in project.playlists:
        if other is playlist:
            continue
        other_real = [e for e in other.entries if e.producer_id]
        if intent.clip_index < len(other_real):
            candidate = other_real[intent.clip_index]
            if candidate.producer_id == orig_producer:
                _rescale(candidate)

    # Keep the tractor length in sync with the (now shorter) content.
    if project.tractor is not None:
        max_len = 0
        for pl in project.playlists:
            total = sum(
                (e.out_point - e.in_point + 1) for e in pl.entries
            )
            max_len = max(max_len, total)
        if max_len > 0:
            project.tractor["out"] = str(max_len - 1)

    logger.info(
        "SetClipSpeed: timewarp %.2fx for clip %d in playlist '%s' (producer %s)",
        intent.speed, intent.clip_index, intent.track_ref, tw_id,
    )


def _tw_producer_id(base: str, speed: float, pitch: bool) -> str:
    """Deterministic id for a timewarp producer at ``speed`` (+ pitch flag)."""
    sid = f"{base}_tw{speed:g}"
    return f"{sid}_pc" if pitch else sid


def _ensure_timewarp_producer(
    project: KdenliveProject,
    source: Producer,
    speed: float,
    pitch: bool,
) -> str:
    """Create (once) a ``timewarp:{speed}`` producer wrapping ``source``.

    Returns the producer id. Reuses the existing :func:`_timewarp_resource`
    helper and mirrors the property shape written by :func:`_apply_set_clip_speed`.
    """
    tw_id = _tw_producer_id(source.id, speed, pitch)
    if any(p.id == tw_id for p in project.producers):
        return tw_id
    tw_resource = _timewarp_resource(source, speed)
    props = {
        "mlt_service": "timewarp",
        "resource": tw_resource,
        "warp_speed": f"{speed:g}",
        "warp_resource": source.resource or source.properties.get("resource", ""),
    }
    if pitch:
        props["warp_pitch"] = "1"
    if "length" in source.properties:
        try:
            src_len = int(source.properties["length"])
            props["length"] = str(max(1, round(src_len / speed)))
        except ValueError:
            pass
    project.producers.append(Producer(id=tw_id, resource=tw_resource, properties=props))
    return tw_id


def _ramp_entries(
    entry: PlaylistEntry,
    segments: list[tuple[int, int, float]],
    project: KdenliveProject,
    source: Producer,
    pitch: bool,
) -> list[PlaylistEntry]:
    """Build the per-segment timewarp entries replacing ``entry``.

    Segment source offsets are relative to ``entry.in_point``; each becomes a
    playlist entry pointing at a ``timewarp:{speed}`` producer with in/out in the
    warped producer's frame space.
    """
    from workshop_video_brain.edit_mcp.pipelines.speed_ramp import timewarp_entry

    new_entries: list[PlaylistEntry] = []
    for src_in, src_out, speed in segments:
        speed = float(speed)
        if speed <= 0 or src_out <= src_in:
            continue
        tw_id = _ensure_timewarp_producer(project, source, speed, pitch)
        tw_in, tw_out = timewarp_entry(entry.in_point, int(src_in), int(src_out), speed)
        new_entries.append(
            PlaylistEntry(producer_id=tw_id, in_point=tw_in, out_point=tw_out)
        )
    return new_entries


def _apply_speed_ramp(project: KdenliveProject, intent: SpeedRamp) -> None:
    """Realise a keyframed speed ramp as a run of constant-speed timewarp slices.

    Kdenlive's UI "Time Remap" keyframes are approximated by slicing the clip at
    ramp boundaries and swapping each slice's producer for a ``timewarp:{speed}``
    producer (the proven :func:`_apply_set_clip_speed` machinery). Linked entries
    (same original producer at the same clip index on another playlist -- e.g. the
    paired audio) are ramped identically so tracks stay in sync.
    """
    playlist = _find_playlist(project, intent.track_ref)
    if playlist is None:
        logger.warning(
            "SpeedRamp: no playlist found with id '%s' – skipped.", intent.track_ref
        )
        return

    real_entries = [e for e in playlist.entries if e.producer_id]
    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "SpeedRamp: clip_index %d out of range – skipped.", intent.clip_index
        )
        return

    segments = [tuple(s) for s in intent.segments]
    if not segments:
        logger.warning("SpeedRamp: no segments supplied – skipped.")
        return

    entry = real_entries[intent.clip_index]
    source = next((p for p in project.producers if p.id == entry.producer_id), None)
    if source is None:
        logger.warning(
            "SpeedRamp: producer '%s' not found – skipped.", entry.producer_id
        )
        return

    orig_producer = entry.producer_id

    def _apply_to(pl: Playlist, target: PlaylistEntry) -> None:
        new_entries = _ramp_entries(
            target, segments, project, source, intent.pitch_compensation
        )
        if not new_entries:
            return
        full_idx = pl.entries.index(target)
        pl.entries[full_idx] = new_entries[0]
        for offset, ne in enumerate(new_entries[1:], start=1):
            pl.entries.insert(full_idx + offset, ne)

    _apply_to(playlist, entry)

    # Ramp any linked copies (paired audio track etc.).
    for other in project.playlists:
        if other is playlist:
            continue
        other_real = [e for e in other.entries if e.producer_id]
        if intent.clip_index < len(other_real):
            candidate = other_real[intent.clip_index]
            if candidate.producer_id == orig_producer:
                _apply_to(other, candidate)

    # Keep the tractor length in sync with the (re-timed) content.
    if project.tractor is not None:
        max_len = 0
        for pl in project.playlists:
            total = sum((e.out_point - e.in_point + 1) for e in pl.entries)
            max_len = max(max_len, total)
        if max_len > 0:
            project.tractor["out"] = str(max_len - 1)

    logger.info(
        "SpeedRamp: %d segments for clip %d in playlist '%s' (producer %s)",
        len(segments), intent.clip_index, intent.track_ref, orig_producer,
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
    dur = max(1, intent.duration_frames)
    clip_len = max(1, entry.out_point - entry.in_point + 1)

    # MLT's ``volume`` filter animates ``level`` in **decibels** (0 = unity,
    # -60 ≈ silence).  Keyframe positions are relative to the clip start.
    _FLOOR = "-60"
    if fade_type == "in":
        level = f"0={_FLOOR};{min(dur, clip_len - 1)}=0"
    else:
        start = max(0, clip_len - 1 - dur)
        level = f"{start}=0;{clip_len - 1}={_FLOOR}"

    track_index = _playlist_index(project, intent.track_ref)
    if track_index is None:
        logger.warning(
            "AudioFade: playlist '%s' not indexable – skipped.", intent.track_ref
        )
        return

    # A real MLT ``volume`` filter with a keyframed ``level`` (gain), nested in
    # the clip <entry> by the serializer (§1.1).  The old ``type="volume"`` had
    # no mlt_service and melt failed to load it.
    xml = (
        f'<filter id="audiofade_{fade_type}_{intent.track_ref}_{intent.clip_index}" '
        f'mlt_service="volume" '
        f'track="{track_index}" '
        f'clip_index="{intent.clip_index}">'
        f'<property name="mlt_service">volume</property>'
        f'<property name="level">{level}</property>'
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


def _set_hide_directive(project: KdenliveProject, track_ref: str, hide: str) -> None:
    """Record a ``hide`` value for a track's tractor entry.

    Represented as a ``<kdenlive:hide>`` OpaqueElement that the serializer
    consumes to set the ``hide`` attribute on the track (the only place MLT
    honours mute/visibility).  A later directive for the same track supersedes
    an earlier one.
    """
    project.opaque_elements = [
        el
        for el in project.opaque_elements
        if not (el.tag == "kdenlive:hide" and f'track="{track_ref}"' in el.xml_string)
    ]
    xml = f'<kdenlive:hide track="{track_ref}" hide="{hide}" />'
    project.opaque_elements.append(
        OpaqueElement(tag="kdenlive:hide", xml_string=xml, position_hint="tractor")
    )


def _apply_set_track_mute(project: KdenliveProject, intent: SetTrackMute) -> None:
    """Mute/unmute a track by setting ``hide`` on its tractor entry."""
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackMute: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    if track.track_type == "audio":
        # Audio tracks default to hide="video"; muting also hides audio.
        hide = "both" if intent.muted else "video"
    else:
        hide = "audio" if intent.muted else ""
    _set_hide_directive(project, intent.track_ref, hide)
    logger.info("SetTrackMute: track '%s' muted=%s", intent.track_ref, intent.muted)


def _apply_set_track_visibility(project: KdenliveProject, intent: SetTrackVisibility) -> None:
    """Show/hide a track by setting ``hide`` on its tractor entry."""
    track = next((t for t in project.tracks if t.id == intent.track_ref), None)
    if track is None:
        logger.warning(
            "SetTrackVisibility: no track found with id '%s' – skipped.", intent.track_ref
        )
        return

    if track.track_type == "audio":
        hide = "video" if intent.visible else "both"
    else:
        hide = "" if intent.visible else "video"
    _set_hide_directive(project, intent.track_ref, hide)
    logger.info(
        "SetTrackVisibility: track '%s' visible=%s", intent.track_ref, intent.visible
    )


def _apply_add_effect(project: KdenliveProject, intent: AddEffect) -> None:
    """Insert an MLT filter element for a clip on a track.

    Builds a <filter mlt_service="..."> XML element with <property> children
    for each param, and appends it as an OpaqueElement.
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

    # Build filter XML
    # Filters are OpaqueElement objects with position_hint="after_tractor",
    # matching the existing SetClipSpeed and AudioFade patterns in the patcher.
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


def _resolve_track_index(project: KdenliveProject, track_ref: str, track_index: int) -> int | None:
    """Resolve a track filter's target playlist index.

    Prefers an explicit non-negative ``track_index``; otherwise looks the
    ``track_ref`` playlist id up. Returns None if neither resolves.
    """
    if track_index is not None and track_index >= 0:
        if track_index < len(project.playlists):
            return track_index
        return None
    return _playlist_index(project, track_ref)


def _track_filter_meta(elem: OpaqueElement) -> tuple[int | None, str, str] | None:
    """Return ``(track_index, filter_id, mlt_service)`` for a track filter opaque.

    A *track* filter is a ``<filter>`` OpaqueElement carrying a ``track``
    attribute but NO ``clip_index`` (the absence is what distinguishes it from a
    clip-scoped filter). Returns None for anything else.
    """
    if elem.tag != "filter":
        return None
    try:
        root = ET.fromstring(elem.xml_string)
    except ET.ParseError:
        return None
    track = root.get("track")
    if track is None or root.get("clip_index") is not None:
        return None
    try:
        tidx = int(track)
    except ValueError:
        return None
    service = root.get("mlt_service") or ""
    for child in root:
        if child.tag == "property" and child.get("name") == "mlt_service":
            service = child.text or service
    return tidx, root.get("id") or "", service


def _apply_clear_track_filters(project: KdenliveProject, intent: ClearTrackFilters) -> None:
    """Remove track-level filters on a track, optionally filtered by id/service."""
    idx = _resolve_track_index(project, intent.track_ref, intent.track_index)
    if idx is None:
        logger.warning(
            "ClearTrackFilters: no track for ref '%s'/index %d – skipped.",
            intent.track_ref, intent.track_index,
        )
        return

    def _keep(el: OpaqueElement) -> bool:
        meta = _track_filter_meta(el)
        if meta is None:
            return True
        tidx, fid, service = meta
        if tidx != idx:
            return True
        if intent.id_prefix and not fid.startswith(intent.id_prefix):
            return True
        if intent.service and service != intent.service:
            return True
        return False  # matches -> drop

    before = len(project.opaque_elements)
    project.opaque_elements = [el for el in project.opaque_elements if _keep(el)]
    logger.info(
        "ClearTrackFilters: track %d removed %d filter(s) (prefix=%r service=%r)",
        idx, before - len(project.opaque_elements), intent.id_prefix, intent.service,
    )


def _apply_add_track_filter(project: KdenliveProject, intent: AddTrackFilter) -> None:
    """Attach an MLT filter to a whole track (nested in its <playlist>).

    The filter is stored as a ``<filter track="{index}" mlt_service="...">``
    OpaqueElement WITHOUT a ``clip_index`` attribute; the serializer relocates it
    into the track's ``<playlist>`` (after entries), the only placement melt
    applies for a track-wide audio effect (§3 "Track-level audio").
    """
    idx = _resolve_track_index(project, intent.track_ref, intent.track_index)
    if idx is None:
        logger.warning(
            "AddTrackFilter: no track for ref '%s'/index %d – skipped.",
            intent.track_ref, intent.track_index,
        )
        return

    fid = intent.filter_id or f"trackfilter_{idx}_{intent.mlt_service}"

    if intent.replace:
        def _keep(el: OpaqueElement) -> bool:
            meta = _track_filter_meta(el)
            if meta is None:
                return True
            tidx, existing_id, _service = meta
            return not (tidx == idx and existing_id == fid)
        project.opaque_elements = [el for el in project.opaque_elements if _keep(el)]

    props_xml = "".join(
        f'<property name="{k}">{v}</property>' for k, v in intent.properties.items()
    )
    xml = (
        f'<filter id="{fid}" '
        f'mlt_service="{intent.mlt_service}" '
        f'track="{idx}">'
        f'{props_xml}'
        f'</filter>'
    )
    project.opaque_elements.append(
        OpaqueElement(tag="filter", xml_string=xml, position_hint="track")
    )
    logger.info(
        "AddTrackFilter: '%s' (id=%s) on track %d", intent.mlt_service, fid, idx
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
        position_hint="tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AddComposition: applied '%s' between tracks %d and %d (frames %d-%d)",
        intent.composition_type, intent.track_a, intent.track_b,
        intent.start_frame, intent.end_frame,
    )


def _resolve_clip_index(real_entries: list, ref: str, default: int = 0) -> int:
    """Resolve a clip reference to a real-entry index.

    ``ref`` may be an integer index (as a string) or a producer id.
    """
    if ref is None or ref == "":
        return default
    try:
        idx = int(ref)
        if 0 <= idx < len(real_entries):
            return idx
    except (TypeError, ValueError):
        pass
    for i, e in enumerate(real_entries):
        if e.producer_id == ref:
            return i
    return default


def _tractor_index(project: KdenliveProject, position: int) -> int:
    """Sequence-tractor track index for the track at ``position``.

    Mirrors the modern (E-shape) serializer: the sequence tractor's track 0 is
    the black background, then each timeline track is ONE lane-wrapper
    ``<tractor>`` slot (the clip + companion lanes are nested inside it), so the
    track at ``position`` maps to sequence slot ``1 + position``.
    """
    return 1 + position


def _emit_simple_transition(project: KdenliveProject, intent: AddTransition) -> None:
    """Fallback: emit a standalone luma transition into the tractor.

    Used when the target clips cannot be resolved (e.g. an empty project).
    """
    service = "luma"
    duration = max(1, intent.duration_frames)
    xml = (
        f'<transition id="transition_{len(project.opaque_elements)}">'
        f'<property name="mlt_service">{service}</property>'
        f'<property name="a_track">0</property>'
        f'<property name="b_track">1</property>'
        f'<property name="in">0</property>'
        f'<property name="out">{duration - 1}</property>'
        f'</transition>'
    )
    project.opaque_elements.append(
        OpaqueElement(tag="transition", xml_string=xml, position_hint="tractor")
    )
    logger.info(
        "Applied fallback %s transition on track '%s' (%d frames)",
        service, intent.track_ref or "0", duration,
    )


def _apply_add_transition(project: KdenliveProject, intent: AddTransition) -> None:
    """Apply a crossfade between two adjacent clips as a real MLT mix.

    The pseudo ``<transition type="crossfade">`` MLT rejected (§1.1) is replaced
    by a genuine ``luma`` transition in the tractor between two overlapping
    video tracks: the right clip is moved onto a new top video track, pulled
    earlier so it overlaps the (extended) left clip, and a ``luma`` transition
    dissolves the lower track into the upper one over the overlap.  The cut is
    the visual midpoint of the transition.
    """
    duration = max(1, intent.duration_frames)
    playlist = _find_playlist(project, intent.track_ref)
    vindex = _playlist_index(project, intent.track_ref)
    if playlist is None or vindex is None:
        _emit_simple_transition(project, intent)
        return

    real = [e for e in playlist.entries if e.producer_id]
    left_idx = _resolve_clip_index(real, intent.left_clip_ref, default=0)
    right_idx = left_idx + 1
    if left_idx < 0 or right_idx >= len(real):
        logger.warning(
            "AddTransition: no adjacent clip pair for ref '%s' in '%s' -- "
            "emitting standalone transition.",
            intent.left_clip_ref, intent.track_ref,
        )
        _emit_simple_transition(project, intent)
        return

    left_entry = real[left_idx]
    right_entry = real[right_idx]

    # Timeline start frames (sum of entry lengths, including blanks, before the
    # target entry in the source playlist).
    left_start = 0
    cut = 0
    seen_left = False
    for e in playlist.entries:
        if e is left_entry:
            seen_left = True
        if e is right_entry:
            break
        if not seen_left:
            left_start += max(0, e.out_point - e.in_point + 1)
        cut += max(0, e.out_point - e.in_point + 1)

    half1 = duration // 2
    half2 = duration - half1

    # Extend the left clip forward by half2 (clamped to the producer length).
    src = next((p for p in project.producers if p.id == left_entry.producer_id), None)
    max_out = left_entry.out_point + half2
    if src is not None and "length" in src.properties:
        try:
            plen = int(src.properties["length"])
            max_out = min(max_out, left_entry.in_point + plen - 1)
        except ValueError:
            pass
    left_entry.out_point = max_out
    left_timeline_end = left_start + (left_entry.out_point - left_entry.in_point + 1) - 1

    lead = max(0, cut - half1)

    # Build the new top video track carrying the right clip (+ any clips that
    # followed it on the source track), preceded by a lead-in blank.
    moved = real[right_idx:]
    moved_ids = {id(e) for e in moved}
    top_entries: list[PlaylistEntry] = []
    if lead > 0:
        top_entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=lead - 1))
    for e in moved:
        top_entries.append(e.model_copy(deep=True))

    # Remove the moved clips from the source playlist.
    playlist.entries = [e for e in playlist.entries if id(e) not in moved_ids]

    top_id = f"{playlist.id}_xfade{len([t for t in project.tracks if 'xfade' in t.id])}"
    project.playlists.append(Playlist(id=top_id, entries=top_entries))

    # Register a matching video track so the serializer builds a tractor slot.
    if project.tracks:
        source_positions = {t.id: i for i, t in enumerate(project.tracks)}
        src_pos = source_positions.get(intent.track_ref, vindex)
        project.tracks.append(Track(id=top_id, track_type="video", name="Crossfade"))
        top_pos = len(project.tracks) - 1
    else:
        # Serializer falls back to playlists-as-tracks; positions are playlist
        # indices.  The new playlist was appended last.
        src_pos = vindex
        top_pos = len(project.playlists) - 1

    # In the E-shape sequence tractor every timeline track composites onto
    # track 0 (the accumulator) via its always-active compositor, so the video
    # track's clip is already on track 0 during the overlap.  The crossfade must
    # dissolve the incoming (top/xfade) track INTO that accumulator, i.e.
    # a_track=0 -- not the source track slot (which would write to a track that
    # never reaches the output).  The xfade track carries no always-active
    # compositor, so this luma is its only route to the output.
    _ = _tractor_index(project, src_pos)  # (retained for logging/back-compat)
    a_track = 0
    b_track = _tractor_index(project, top_pos)
    t_in = max(0, cut - half1)
    t_out = left_timeline_end  # end of the (extended) left clip on the timeline

    xml = (
        f'<transition id="transition_{len(project.opaque_elements)}">'
        f'<property name="mlt_service">luma</property>'
        f'<property name="a_track">{a_track}</property>'
        f'<property name="b_track">{b_track}</property>'
        f'<property name="in">{t_in}</property>'
        f'<property name="out">{t_out}</property>'
        f'</transition>'
    )
    project.opaque_elements.append(
        OpaqueElement(tag="transition", xml_string=xml, position_hint="tractor")
    )
    logger.info(
        "AddTransition: luma crossfade a_track=%d b_track=%d in=%d out=%d "
        "(cut=%d, %d frames) on '%s'",
        a_track, b_track, t_in, t_out, cut, duration, intent.track_ref,
    )

