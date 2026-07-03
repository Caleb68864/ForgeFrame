"""Multicam MCP tools: ``multicam_assemble`` (Phase A2) + ``multicam_switch`` (Phase B).

Orchestrates the multicam workflow on top of two shipped primitives --
``media_sync_by_audio`` (audio offset recovery) and ``clip_place`` (frame-exact
timeline placement).  Spec:
``docs/research/2026-07-03-tutorial-effect-analysis/multicam.md`` §3, phases A2
and B (both marked BUILDABLE now the placement-fix has landed).

* ``multicam_assemble`` -- probe/sync every angle against the reference via the
  ``audio_sync`` pipeline, then stack each angle on its own new video track at the
  recovered leading-gap offset using ``PlaceClip`` intents (the canonical
  clip_place engine, not a private insert).  Returns the per-angle offset report.
* ``multicam_switch`` -- scripted switch-cutting.  Builds a top *program* track and
  ``clip_place``-overwrites the active angle's footage onto it for each cut
  segment.  See ``pipelines/multicam`` for the approach rationale + tradeoff.

Pure parsing/planning lives in ``pipelines/multicam.py``; this module does the
I/O (audio sync, ffprobe duration, snapshot, patch, serialise) and returns
``_ok`` / ``_err`` envelopes.  Registered by the ``bundles`` auto-importer.
Touches no ``adapters/kdenlive/`` code, no ``server/tools.py``.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
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
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
)
from workshop_video_brain.edit_mcp.pipelines import multicam as mc
from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
from workshop_video_brain.edit_mcp.pipelines.audio_sync import (
    DEFAULT_WINDOW_SECONDS,
    sync_by_audio,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _producer_id_for(media_path: Path) -> str:
    """Deterministic producer id from a media path (mirrors ``clip_place``)."""
    stem = media_path.stem or "angle"
    h = hashlib.md5(str(media_path).encode()).hexdigest()[:6]
    return f"{stem}_{h}"


def _probe_duration_seconds(media_path: Path) -> float | None:
    """Best-effort media duration in seconds via ffprobe (None if unavailable)."""
    if not shutil.which("ffprobe"):
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(media_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and stream.get("duration"):
                return float(stream["duration"])
        dur = data.get("format", {}).get("duration")
        return float(dur) if dur else None
    except Exception:
        return None


def _load(workspace_path: str, project_file: str):
    """Validate the workspace and parse the project file."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    ws_path, _ws = _require_workspace(workspace_path)
    project_path = ws_path / project_file
    if not project_path.exists():
        raise FileNotFoundError(f"Project file not found: {project_file}")
    return ws_path, project_path, parse_project(project_path)


def _resolve(ws_path: Path, source: str) -> Path:
    p = Path(source)
    if not p.is_absolute():
        p = ws_path / source
    return p


def _video_playlist_indices(project) -> list[int]:
    """Indices into ``project.playlists`` of the video (non-audio) tracks."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [i for i, pl in enumerate(project.playlists) if pl.id not in audio_ids]


def _unique_track_id(project, base: str) -> str:
    used = {t.id for t in project.tracks} | {p.id for p in project.playlists}
    if base not in used:
        return base
    n = 1
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


# ---------------------------------------------------------------------------
# multicam_assemble (Phase A2)
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def multicam_assemble(
    workspace_path: str,
    project_file: str,
    sources: str,
    reference: int = 0,
    sync: str = "audio",
) -> dict:
    """Stack + sync N camera angles onto their own timeline tracks.

    Recovers each non-reference angle's start offset against the reference (audio
    cross-correlation via the ``media_sync_by_audio`` pipeline), then places every
    angle on its own new video track at the recovered leading-gap offset using the
    canonical ``clip_place`` engine, so the shared moment lines up vertically
    across all tracks.

    Args:
        workspace_path: Workspace root.
        project_file: ``.kdenlive`` project, relative to the workspace.
        sources: The angle recordings -- a JSON array or a comma/newline list of
            media paths (absolute, or relative to the workspace).  Order defines
            the angle indices; ``sources[reference]`` is the sync reference.
        reference: Index into ``sources`` of the reference angle (default 0).
        sync: ``"audio"`` (default; recover offsets by audio correlation) or
            ``"none"``/``"manual"`` (stack every angle at frame 0, no sync).

    Returns a success dict with the per-angle offset/gap/track report + snapshot
    id, or an error dict.
    """
    from workshop_video_brain.core.models.kdenlive import Track, Playlist
    from workshop_video_brain.core.models.timeline import PlaceClip
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        paths = mc.parse_source_list(sources)
    except ValueError as exc:
        return err(str(exc), error_type=BAD_JSON_PARAM, suggestion='Provide sources as a JSON array or a comma/newline list, e.g. ["/clips/a.mp4", "/clips/b.mp4"].', given=sources)
    if len(paths) < 2:
        return invalid_input("multicam needs at least 2 sources to stack", suggestion="Provide at least two angle recordings in sources (JSON array or comma/newline list).", given=sources)

    sync_mode = (sync or "audio").lower()
    if sync_mode not in ("audio", "none", "manual"):
        return _err(f"unknown sync mode {sync!r}; use 'audio' or 'none'")

    if reference < 0 or reference >= len(paths):
        return _err(
            f"reference {reference} out of range (got {len(paths)} sources)"
        )

    try:
        ws_path, project_path, project = _load(workspace_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    resolved = [_resolve(ws_path, s) for s in paths]
    for p in resolved:
        if not p.exists():
            return _err(f"source not found: {p}")

    fps = project.profile.fps or 25.0

    # 1. Recover per-angle offsets against the reference.
    offsets: list[float] = [0.0] * len(resolved)
    confidences: list[float | None] = [None] * len(resolved)
    confidences[reference] = 1.0
    if sync_mode == "audio":
        ref_path = resolved[reference]
        for i, path in enumerate(resolved):
            if i == reference:
                continue
            res = sync_by_audio(
                ref_path, path, method="correlate", window_seconds=DEFAULT_WINDOW_SECONDS
            )
            if not res.get("success"):
                return _err(
                    f"audio sync failed for angle {i} ({path.name}): "
                    f"{res.get('error', 'unknown error')}"
                )
            offsets[i] = float(res["offset_seconds"])
            confidences[i] = float(res["confidence"])

    # 2. Offsets -> per-track leading-gap frames.
    try:
        gaps = mc.compute_alignment(offsets, fps)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # 3. Source durations -> clip lengths in frames.
    lengths: list[int] = []
    for path in resolved:
        dur = _probe_duration_seconds(path)
        if dur is None or dur <= 0:
            return _err(
                f"could not probe a positive duration for {path} "
                f"(ffprobe unavailable or unreadable media)"
            )
        lengths.append(max(1, cp.seconds_to_frames(dur, fps)))

    # 4. Snapshot before writing.
    try:
        snap = create_snapshot(ws_path, project_path, description="before_multicam_assemble")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    # 5. Add one video track per angle, then place each angle via clip_place.
    base_index = len(project.playlists)
    intents = []
    report = []
    for i, path in enumerate(resolved):
        track_id = _unique_track_id(project, f"multicam_angle_{i}")
        project.tracks.append(Track(id=track_id, track_type="video", name=f"Angle {i}"))
        project.playlists.append(Playlist(id=track_id))
        producer_id = _producer_id_for(path)
        intents.append(
            PlaceClip(
                track_ref=track_id,
                producer_id=producer_id,
                source_path=str(path),
                in_point=0,
                out_point=lengths[i] - 1,
                at_frame=gaps[i],
                mode="overwrite",
            )
        )
        report.append({
            "angle": i,
            "source": str(path),
            "is_reference": i == reference,
            "offset_seconds": round(offsets[i], 4),
            "confidence": (round(confidences[i], 4) if confidences[i] is not None else None),
            "gap_frames": gaps[i],
            "length_frames": lengths[i],
            "track_index": base_index + i,
            "playlist_id": track_id,
        })

    try:
        patched = patcher.patch_project(project, intents)
    except (ValueError, IndexError) as exc:
        return _err(f"failed to stack angles: {exc}")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "reference": reference,
        "sync": sync_mode,
        "fps": fps,
        "angle_count": len(resolved),
        "angles": report,
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# multicam_switch (Phase B)
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def multicam_switch(
    workspace_path: str,
    project_file: str,
    cuts: str,
    angle_tracks: str = "",
) -> dict:
    """Scripted angle switch-cutting onto a top *program* track.

    Given a stacked/synced multicam project and an ordered list of switch points,
    builds a dedicated top video track and ``clip_place``-overwrites the active
    angle's footage onto it for each cut segment.  The program track is the
    switched output; it composites over the stacked angle tracks below.

    Args:
        workspace_path: Workspace root.
        project_file: ``.kdenlive`` project, relative to the workspace.
        cuts: A JSON array ``[{"at_seconds": <float>, "angle": <int>}, ...]`` of
            switch points -- from each ``at_seconds`` the given ``angle`` is shown
            until the next cut (or the end of the timeline).
        angle_tracks: Optional mapping of angle index -> playlist (track) index, as
            a JSON array or comma list (e.g. ``"3,4,5"`` => angle 0 is track 3).
            Empty (default) auto-maps angle *k* to the *k*-th video track that
            holds footage, in track order.

    Returns a success dict with the program-track index and the resolved segment
    list + snapshot id, or an error dict.
    """
    from workshop_video_brain.core.models.kdenlive import Track, Playlist
    from workshop_video_brain.core.models.timeline import PlaceClip
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        parsed_cuts = mc.parse_cuts(cuts)
    except ValueError as exc:
        return err(str(exc), error_type=BAD_JSON_PARAM, suggestion='Provide cuts as JSON, e.g. [{"at_seconds": 0, "angle": 0}, {"at_seconds": 4.0, "angle": 1}].', given=cuts)
    try:
        angle_track_map = mc.parse_int_list(angle_tracks)
    except ValueError as exc:
        return _err(f"invalid angle_tracks: {exc}")

    try:
        ws_path, project_path, project = _load(workspace_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    fps = project.profile.fps or 25.0

    # Resolve the angle-index -> playlist-index mapping.
    if angle_track_map:
        for idx in angle_track_map:
            if idx < 0 or idx >= len(project.playlists):
                return _err(f"angle_tracks references track {idx} out of range")
        angle_map = angle_track_map
    else:
        angle_map = [
            i for i in _video_playlist_indices(project)
            if any(e.producer_id for e in project.playlists[i].entries)
        ]
        if not angle_map:
            return _err("no video tracks with footage found to switch between")

    max_angle = max(c.angle for c in parsed_cuts)
    if max_angle >= len(angle_map):
        return _err(
            f"cut references angle {max_angle} but only {len(angle_map)} angle "
            f"track(s) are available"
        )

    timeline_end = max(
        (cp.playlist_length(pl.entries) for pl in project.playlists), default=0
    )
    try:
        segments = mc.build_switch_segments(parsed_cuts, timeline_end, fps)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Locate each segment's source footage before mutating anything.
    placements = []  # (at_frame, producer_id, in_point, out_point, end, angle)
    for seg in segments:
        pl_index = angle_map[seg.angle]
        loc = mc.locate_source(project.playlists[pl_index].entries, seg.start_frame)
        if loc is None:
            return _err(
                f"angle {seg.angle} (track {pl_index}) has no footage at frame "
                f"{seg.start_frame}"
            )
        end = min(seg.end_frame, loc.available_end)
        if end <= seg.start_frame:
            continue
        length = end - seg.start_frame
        placements.append((
            seg.start_frame, loc.producer_id, loc.in_point,
            loc.in_point + length - 1, end, seg.angle,
        ))
    if not placements:
        return _err("no renderable program segments after locating angle footage")

    try:
        snap = create_snapshot(ws_path, project_path, description="before_multicam_switch")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    # Create the top program track and overwrite-place each segment's angle onto it.
    program_id = _unique_track_id(project, "multicam_program")
    project.tracks.append(Track(id=program_id, track_type="video", name="Program"))
    project.playlists.append(Playlist(id=program_id))
    program_index = len(project.playlists) - 1

    intents = []
    seg_report = []
    for at_frame, producer_id, in_pt, out_pt, end, angle in placements:
        intents.append(
            PlaceClip(
                track_ref=program_id,
                producer_id=producer_id,
                source_path="",
                in_point=in_pt,
                out_point=out_pt,
                at_frame=at_frame,
                mode="overwrite",
            )
        )
        seg_report.append({
            "start_frame": at_frame,
            "end_frame": end,
            "angle": angle,
            "producer_id": producer_id,
        })

    try:
        patched = patcher.patch_project(project, intents)
    except (ValueError, IndexError) as exc:
        return _err(f"failed to build program track: {exc}")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "program_track": program_index,
        "program_playlist_id": program_id,
        "angle_tracks": angle_map,
        "segment_count": len(seg_report),
        "segments": seg_report,
        "snapshot_id": snapshot_id,
    })
