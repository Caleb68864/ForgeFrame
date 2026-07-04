"""``clip_place`` -- absolute-time timeline placement bundle.

The canonical, public timeline-placement engine (SYNTHESIS gap #6 / gap-analysis
item 1).  Where ``clip_insert`` can only *append* media to the first video track
at a playlist index, these tools place a clip at an exact time ``T`` on a chosen
track, with overwrite-vs-insert semantics, cross-track moves, and match-length
inserts -- the "cover this A-roll segment with this B-roll" move real assembly
needs.

Three tools:

* ``clip_place`` -- place a clip at ``at_seconds`` on ``track`` (overwrite the
  region, or insert + ripple).  ``source_or_producer`` is either a media path
  (a producer is registered, reusing the deterministic-id + ffprobe machinery)
  or an existing producer id.
* ``clip_move_to`` -- cross-track move (today's ``clip_move`` is same-track only):
  lift a clip off one track and drop it on another via the same engine.
* ``clip_place_matched`` -- match-length insert: cut the B-roll to exactly the
  duration of a reference clip on another track.

All placement arithmetic is pure (``pipelines/clip_place.py``); this module only
does the I/O: parse, probe media, snapshot, patch, serialise.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
    parse_project,
    ProjectParseError,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    probe_duration_seconds as _probe_duration_seconds,
)
from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
from workshop_video_brain.workspace import create_snapshot


# ---------------------------------------------------------------------------
# media / producer helpers
# ---------------------------------------------------------------------------

def _producer_id_for(media_path: Path) -> str:
    """Deterministic producer id from a media path (stem + short hash).

    Mirrors ``clip_insert`` / ``overlay_looks.overlay_producer_id`` so re-placing
    the same media reuses one producer.
    """
    stem = media_path.stem or "clip"
    h = hashlib.md5(str(media_path).encode()).hexdigest()[:6]
    return f"{stem}_{h}"


def _producer_length_frames(project, producer_id: str, fps: float) -> int | None:
    """Return a producer's declared ``length`` in frames, if present."""
    for p in project.producers:
        if p.id == producer_id:
            val = p.properties.get("length")
            if val:
                try:
                    return int(val)
                except ValueError:
                    return None
    return None


def _resolve_source(
    project, source_or_producer: str, ws_path: Path
) -> tuple[str, str, float | None]:
    """Resolve ``source_or_producer`` to ``(producer_id, source_path, duration_s)``.

    If it matches an existing producer id, that producer is reused (no media
    path, duration probed from its declared length by the caller).  Otherwise it
    is treated as a media path: a deterministic producer id is derived and the
    media duration is probed with ffprobe.
    """
    if any(p.id == source_or_producer for p in project.producers):
        return source_or_producer, "", None
    media = Path(source_or_producer)
    if not media.is_absolute():
        candidate = ws_path / source_or_producer
        media = candidate if candidate.exists() else media
    return _producer_id_for(media), str(media), _probe_duration_seconds(media)


def _load(workspace_path: str, project_file: str):
    """Shared load: validate workspace, parse the project file."""
    ws_path, _ws = _require_workspace(workspace_path)
    project_path = ws_path / project_file
    if not project_path.exists():
        raise FileNotFoundError(f"Project file not found: {project_file}")
    return ws_path, project_path, parse_project(project_path)


def _resolve_track(project, track: int):
    """Return the playlist at index ``track`` or raise ValueError."""
    if track < 0 or track >= len(project.playlists):
        raise ValueError(
            f"track {track} out of range (project has {len(project.playlists)} tracks)"
        )
    return project.playlists[track]


# ---------------------------------------------------------------------------
# clip_place
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def clip_place(
    workspace_path: str,
    project_file: str,
    source_or_producer: str,
    track: int,
    at_seconds: float,
    in_seconds: float = 0.0,
    out_seconds: float | None = None,
    mode: str = "overwrite",
    ripple_all_tracks: bool = False,
) -> dict:
    """Place a clip at absolute time ``at_seconds`` on ``track``.

    Args:
        workspace_path: Workspace root.
        project_file: Project file relative to the workspace (e.g.
            ``projects/working_copies/foo.kdenlive``).
        source_or_producer: A media path (a producer is registered if absent,
            reusing the ingest/producer machinery) OR an existing producer id.
        track: Playlist / track index the clip is placed on (0 = first).
        at_seconds: Absolute timeline time at which the clip starts.
        in_seconds: In-point within the source (default: start).
        out_seconds: Out-point within the source (default: full source length,
            probed via ffprobe or the producer's declared length).
        mode: ``"overwrite"`` (replace the region ``[T, T+len)`` on this track)
            or ``"insert"`` (split at ``T`` and ripple this track right).
        ripple_all_tracks: Insert mode only -- also shift every other track and
            all guides at/after ``T`` right by the clip length, keeping the whole
            timeline in sync (cross-track).

    Returns a success dict with the placed real-clip index, frame span, expected
    timeline length, and snapshot id -- or an error dict.
    """
    try:
        ws_path, project_path, project = _load(workspace_path, project_file)
    except ProjectParseError as exc:
        return corrupt_project(str(getattr(exc, "path", "") or project_file), exc)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if mode not in ("overwrite", "insert"):
        return err(f"mode must be 'overwrite' or 'insert', got {mode!r}", suggestion="Pass mode='overwrite' to replace whatever is under the clip, or mode='insert' to push later clips right.")

    try:
        playlist = _resolve_track(project, track)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    fps = project.profile.fps or 25.0
    producer_id, source_path, duration_s = _resolve_source(
        project, source_or_producer, ws_path
    )

    # If the source resolved to a media *path* (not an existing producer id) and
    # that file does not exist, fail loudly naming the file instead of silently
    # placing a clip that references missing media (which would only surface as a
    # cryptic melt error at render time) or bailing with a confusing
    # "duration unknown" message.
    if source_path and not Path(source_path).exists():
        return missing_file(source_path, "source media")

    try:
        at_frame = cp.seconds_to_frames(at_seconds, fps)
        in_point = cp.seconds_to_frames(in_seconds, fps)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if out_seconds is not None:
        out_point = cp.seconds_to_frames(out_seconds, fps) - 1
    elif duration_s is not None:
        out_point = cp.seconds_to_frames(duration_s, fps) - 1
    else:
        plen = _producer_length_frames(project, producer_id, fps)
        if plen is None:
            return err(
                "out_seconds was not given and the source duration is unknown "
                "(ffprobe is unavailable and the producer has no 'length').",
                suggestion="Pass out_seconds explicitly, or install ffprobe so the duration can be detected automatically.",
            )
        out_point = in_point + plen - 1

    if out_point < in_point:
        return err(
            f"The computed out frame ({out_point}) is before the in frame ({in_point}).",
            suggestion="out_seconds must be greater than in_seconds; check the in/out points you passed.",
        )

    try:
        snap = create_snapshot(ws_path, project_path, description="before_clip_place")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    from workshop_video_brain.core.models.timeline import PlaceClip

    intent = PlaceClip(
        track_ref=playlist.id,
        producer_id=producer_id,
        source_path=source_path,
        in_point=in_point,
        out_point=out_point,
        at_frame=at_frame,
        mode=mode,
        ripple_all_tracks=ripple_all_tracks,
    )
    try:
        patched = patcher.patch_project(project, [intent])
    except (ValueError, IndexError) as exc:
        return err(f"failed to place clip: {exc}", suggestion="Check the target track exists and the timing is valid (project_summary shows the tracks); the one-line cause above says what failed.")
    serialize_project(patched, project_path)

    placed = next(
        (pl for pl in patched.playlists if pl.id == playlist.id), None
    )
    real = [e for e in placed.entries if e.producer_id] if placed else []
    length_frames = out_point - in_point + 1
    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "playlist_id": playlist.id,
        "producer_id": producer_id,
        "mode": mode,
        "at_frame": at_frame,
        "in_frame": in_point,
        "out_frame": out_point,
        "clip_length_frames": length_frames,
        "clip_count_after": len(real),
        "ripple_all_tracks": ripple_all_tracks,
        "timeline_frames": cp.playlist_length(placed.entries) if placed else 0,
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# clip_move_to
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def clip_move_to(
    workspace_path: str,
    project_file: str,
    from_track: int,
    clip_index: int,
    to_track: int,
    at_seconds: float | None = None,
    mode: str = "overwrite",
    close_gap: bool = False,
) -> dict:
    """Move a clip from one track to another (cross-track move).

    Args:
        workspace_path: Workspace root.
        project_file: Project file relative to the workspace.
        from_track: Source track (playlist index).
        clip_index: Index of the real clip on the source track.
        to_track: Target track (playlist index).
        at_seconds: Absolute time on the target (default: keep the clip's
            original timeline start).
        mode: ``"overwrite"`` or ``"insert"`` placement on the target track.
        close_gap: When True the source gap is closed (following clips ripple
            left); otherwise a same-length blank is left so the source keeps its
            layout.

    Returns a success dict with the source/target tracks and the target frame,
    or an error dict.
    """
    try:
        ws_path, project_path, project = _load(workspace_path, project_file)
    except ProjectParseError as exc:
        return corrupt_project(str(getattr(exc, "path", "") or project_file), exc)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if mode not in ("overwrite", "insert"):
        return err(f"mode must be 'overwrite' or 'insert', got {mode!r}", suggestion="Pass mode='overwrite' to replace whatever is under the clip, or mode='insert' to push later clips right.")
    try:
        src = _resolve_track(project, from_track)
        dst = _resolve_track(project, to_track)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    if from_track == to_track:
        return err("from_track and to_track are the same track.", suggestion="Use clip_move for same-track moves; clip_place across tracks needs a different to_track.")

    try:
        cp.clip_at_index(src.entries, clip_index)  # validate
    except IndexError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    fps = project.profile.fps or 25.0
    at_frame = -1
    if at_seconds is not None:
        try:
            at_frame = cp.seconds_to_frames(at_seconds, fps)
        except ValueError as exc:
            return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    try:
        snap = create_snapshot(ws_path, project_path, description="before_clip_move_to")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    from workshop_video_brain.core.models.timeline import MoveClipToTrack

    intent = MoveClipToTrack(
        from_track_ref=src.id,
        clip_index=clip_index,
        to_track_ref=dst.id,
        at_frame=at_frame,
        mode=mode,
        close_gap=close_gap,
    )
    try:
        patched = patcher.patch_project(project, [intent])
    except (ValueError, IndexError) as exc:
        return err(f"failed to move clip: {exc}", suggestion="Check the source clip index and destination track/timing (project_summary lists them); the one-line cause above says what failed.")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "from_track": from_track,
        "from_playlist_id": src.id,
        "clip_index": clip_index,
        "to_track": to_track,
        "to_playlist_id": dst.id,
        "at_frame": at_frame,
        "mode": mode,
        "close_gap": close_gap,
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# clip_place_matched
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def clip_place_matched(
    workspace_path: str,
    project_file: str,
    source: str,
    track: int,
    match_track: int,
    match_clip_index: int,
    mode: str = "overwrite",
) -> dict:
    """Place a clip cut to exactly the duration of a reference clip.

    The reference is the real clip at ``match_clip_index`` on ``match_track``;
    the source is placed on ``track`` at the reference's start time, trimmed to
    the reference's length -- the "cover this A-roll segment with B-roll" move.

    Args:
        workspace_path: Workspace root.
        project_file: Project file relative to the workspace.
        source: Media path (producer registered if absent) or existing producer id.
        track: Track to place the B-roll on (playlist index).
        match_track: Track holding the reference clip (playlist index).
        match_clip_index: Index of the reference clip on ``match_track``.
        mode: ``"overwrite"`` or ``"insert"`` placement.

    Returns a success dict including the matched length and the assertion that
    the placed clip length equals the reference length, or an error dict.
    """
    try:
        ws_path, project_path, project = _load(workspace_path, project_file)
    except ProjectParseError as exc:
        return corrupt_project(str(getattr(exc, "path", "") or project_file), exc)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if mode not in ("overwrite", "insert"):
        return err(f"mode must be 'overwrite' or 'insert', got {mode!r}", suggestion="Pass mode='overwrite' to replace whatever is under the clip, or mode='insert' to push later clips right.")
    try:
        playlist = _resolve_track(project, track)
        ref_playlist = _resolve_track(project, match_track)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    try:
        ref_length = cp.reference_length(ref_playlist.entries, match_clip_index)
        ref_start = cp.clip_start_frame(ref_playlist.entries, match_clip_index)
    except IndexError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    fps = project.profile.fps or 25.0
    producer_id, source_path, _duration_s = _resolve_source(project, source, ws_path)

    # Reject a missing media source before touching the project (see clip_place).
    if source_path and not Path(source_path).exists():
        return missing_file(source_path, "source media")

    # Match length exactly: in-point 0, out-point ref_length - 1.
    in_point = 0
    out_point = ref_length - 1

    try:
        snap = create_snapshot(ws_path, project_path, description="before_clip_place_matched")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    from workshop_video_brain.core.models.timeline import PlaceClip

    intent = PlaceClip(
        track_ref=playlist.id,
        producer_id=producer_id,
        source_path=source_path,
        in_point=in_point,
        out_point=out_point,
        at_frame=ref_start,
        mode=mode,
    )
    try:
        patched = patcher.patch_project(project, [intent])
    except (ValueError, IndexError) as exc:
        return err(f"failed to place matched clip: {exc}", suggestion="Check the matched source and destination track/timing; the one-line cause above says what failed.")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "playlist_id": playlist.id,
        "producer_id": producer_id,
        "match_track": match_track,
        "match_clip_index": match_clip_index,
        "matched_length_frames": ref_length,
        "placed_length_frames": out_point - in_point + 1,
        "at_frame": ref_start,
        "mode": mode,
        "snapshot_id": snapshot_id,
    })
