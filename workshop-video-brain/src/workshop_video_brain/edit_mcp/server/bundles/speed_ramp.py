"""``speed_ramp`` -- keyframed speed ramping / time remapping bundle.

Derived from two Kdenlive tutorials -- "How to Apply Speed Ramping in Kdenlive
2025?" (https://www.youtube.com/watch?v=0yr_lMTticU) and "Slow Motion in Kdenlive
- Time Remapping Tutorial" (https://www.youtube.com/watch?v=o69g-U1OAVI). Both
drive Kdenlive's **Time Remap** panel: keyframes map output-time to source-time,
and the slope between keyframes is the local playback speed (drag a keyframe left
to compress/accelerate, right to stretch/slow). Accelerating a segment shortens
the clip on the timeline; slowing lengthens it.

MLT can express that natively with a ``timeremap`` *link*, but links only live
inside a ``<chain>`` and this project's serializer emits plain ``<producer>``
elements, so the native route is not writable without serializer changes. The
melt-proven, serializer-compatible route (verified: a 2x segment renders to half
its frames) is to slice the clip at ramp boundaries and play each slice through a
constant-speed ``timewarp:{speed}`` producer -- the same machinery ``clip_speed``
uses. A smooth ease is approximated by subdividing each keyframe interval into
many short constant-speed sub-segments. All planning is pure
(``pipelines/speed_ramp.py``); this module only parses/patches/serialises.
"""
from __future__ import annotations

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
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr
from workshop_video_brain.workspace import create_snapshot


def _apply_timeremap_engine(project, playlist, entry, segments, *, image_mode, pitch):
    """Rewrite ``entry`` to play its source through a native ``timeremap`` chain.

    Builds a ``<chain>`` producer wrapping the clip's source with an animated
    ``speed_map`` link and re-points the playlist entry at it (``in=0``,
    ``out=total-1``). Returns the new total output frame count. Assumes the clip
    starts at source in-point 0 (the chain re-loads the full resource).
    """
    from workshop_video_brain.core.models.kdenlive import Link, Producer

    src = next((p for p in project.producers if p.id == entry.producer_id), None)
    if src is None:
        raise ValueError(f"source producer {entry.producer_id!r} not found for timeremap")

    speed_map, total = sr.speed_map_from_segments(segments)
    link_props = sr.timeremap_link_properties(
        speed_map, image_mode=image_mode, pitch=pitch
    )

    chain_id = f"{entry.producer_id}_timeremap_{playlist.id}_{entry.in_point}"
    chain_props: dict[str, str] = {}
    if src.properties.get("mlt_service"):
        chain_props["mlt_service"] = src.properties["mlt_service"]
    chain_props["length"] = str(total)
    chain = Producer(
        id=chain_id,
        resource=src.resource,
        properties=chain_props,
        links=[Link(mlt_service="timeremap", properties=link_props)],
        chain_out=total - 1,
    )
    project.producers.append(chain)

    entry.producer_id = chain_id
    entry.in_point = 0
    entry.out_point = total - 1
    return total


@mcp.tool()
@tool_guard
def speed_ramp(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    keyframes: str,
    easing: str = "cubic",
    pitch_compensation: bool = False,
    engine: str = "segments",
    image_mode: str = "nearest",
) -> dict:
    """Apply a keyframed speed ramp (time remap) to a clip.

    The clip is sliced at ramp boundaries and each slice is played through a
    constant-speed ``timewarp:`` producer, so accelerated parts shorten and
    slowed parts lengthen the clip on the timeline -- reproducing Kdenlive's Time
    Remap. The paired audio entry (same clip index on another track) is ramped in
    lock-step.

    Args:
        workspace_path: Workspace root.
        project_file: Project file relative to the workspace (e.g.
            ``projects/working_copies/foo.kdenlive``).
        track: Playlist / track index the clip lives on.
        clip_index: Index of the clip within that track (real clips only).
        keyframes: JSON array. Two schemas are accepted:
            * speed:  ``[{"at_seconds": t, "speed": v}, ...]`` -- at source-time
              ``t`` (offset within the clip) the playback speed is ``v`` (2.0 =
              2x faster, 0.5 = slow motion); speed eases between keyframes.
            * timemap: ``[{"output_seconds": o, "source_seconds": s}, ...]`` --
              at output-time ``o`` show source-time ``s``; each pair is a
              constant speed ``(s2-s1)/(o2-o1)`` (easing not applied).
        easing: Ramp curve between speed keyframes -- ``cubic`` (smoothstep,
            default), ``linear``, ``ease_in``, or ``ease_out``.
        pitch_compensation: When True, keep audio pitch constant across the
            speed change (``timewarp`` ``warp_pitch`` for the segments engine,
            the timeremap link ``pitch`` boolean for the native engine).
        engine: ``segments`` (default) slices the clip into constant-speed
            ``timewarp:`` producers; ``timeremap`` emits a single native
            ``<chain>`` + ``<link mlt_service="timeremap">`` carrying an animated
            ``speed_map`` for a continuous eased curve.
        image_mode: Timeremap-only -- ``nearest`` (default) or ``blend``
            (frame-blend for motion-blurred slow-mo). Ignored by the segments
            engine.

    Returns a success dict with the engine, segment count, expected timeline
    frames / seconds, source frames covered, keyframe format, and snapshot id --
    or an error dict.
    """
    if engine not in ("segments", "timeremap"):
        return err(f"engine {engine!r} must be 'segments' or 'timeremap'", suggestion="Pass engine='segments' (cut into speed steps) or engine='timeremap' (smooth ramp).")
    if image_mode not in sr.IMAGE_MODES:
        return err(f"image_mode {image_mode!r} must be one of {sr.IMAGE_MODES}", suggestion=f"Pass image_mode as one of: {sr.IMAGE_MODES}.")
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    project = parse_project(project_path)

    n_tracks = len(project.playlists)
    if track < 0 or track >= n_tracks:
        return err(
            f"track {track} out of range (project has {n_tracks} tracks)",
            error_type=INVALID_INDEX,
            suggestion=f"Pass a track index within 0-{max(0, n_tracks - 1)}.",
            given=track, valid_range=f"0-{max(0, n_tracks - 1)}",
        )
    playlist = project.playlists[track]
    real_entries = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        return err(
            f"clip_index {clip_index} out of range (track has {len(real_entries)} clips)",
            error_type=INVALID_INDEX,
            suggestion=f"Pass a clip_index within 0-{max(0, len(real_entries) - 1)}.",
            given=clip_index, valid_range=f"0-{max(0, len(real_entries) - 1)}",
        )
    entry = real_entries[clip_index]
    clip_frames = entry.out_point - entry.in_point + 1
    fps = project.profile.fps or 25.0

    # Pure planning -- raises ValueError on bad keyframes / easing.
    try:
        segments = sr.plan_segments(
            keyframes, clip_frames=clip_frames, fps=fps, easing=easing
        )
        kf_format = sr.keyframe_format(sr.parse_keyframes(keyframes))
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    seg_tuples = [(s.src_in, s.src_out, s.speed) for s in segments]
    src_frames, output_frames = sr.source_output_frames(segments)

    # Snapshot before mutating the project.
    try:
        snap = create_snapshot(ws_path, project_path, description="before_speed_ramp")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    if engine == "timeremap":
        try:
            output_frames = _apply_timeremap_engine(
                project, playlist, entry, segments,
                image_mode=image_mode, pitch=pitch_compensation,
            )
        except (ValueError, IndexError) as exc:
            return err(f"failed to apply timeremap ramp: {exc}", suggestion="Check the clip index and ramp keyframes are valid; the one-line cause above says what failed. Restore the pre-op snapshot with snapshot_restore if needed.")
        patched = project
    else:
        from workshop_video_brain.core.models.timeline import SpeedRamp

        intent = SpeedRamp(
            track_ref=playlist.id,
            clip_index=clip_index,
            segments=seg_tuples,
            pitch_compensation=pitch_compensation,
        )
        try:
            patched = patcher.patch_project(project, [intent])
        except (ValueError, IndexError) as exc:
            return err(f"failed to apply speed ramp: {exc}", suggestion="Check the clip index and speed points are valid; the one-line cause above says what failed. Restore the pre-op snapshot with snapshot_restore if needed.")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "clip_index": clip_index,
        "playlist_id": playlist.id,
        "engine": engine,
        "keyframe_format": kf_format,
        "easing": easing,
        "pitch_compensation": pitch_compensation,
        "image_mode": image_mode if engine == "timeremap" else None,
        "segment_count": len(seg_tuples),
        "source_frames": src_frames,
        "expected_output_frames": output_frames,
        "expected_output_seconds": round(output_frames / fps, 3),
        "original_clip_frames": clip_frames,
        "snapshot_id": snapshot_id,
    })
