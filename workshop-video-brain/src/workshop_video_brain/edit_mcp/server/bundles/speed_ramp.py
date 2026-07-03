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
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr
from workshop_video_brain.workspace import create_snapshot


@mcp.tool()
def speed_ramp(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    keyframes: str,
    easing: str = "cubic",
    pitch_compensation: bool = False,
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
            speed change (MLT ``warp_pitch``); otherwise pitch shifts with speed.

    Returns a success dict with the segment count, expected timeline frames /
    seconds, source frames covered, keyframe format, and snapshot id -- or an
    error dict.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project_path = ws_path / project_file
    if not project_path.exists():
        return _err(f"Project file not found: {project_file}")

    project = parse_project(project_path)

    if track < 0 or track >= len(project.playlists):
        return _err(
            f"track {track} out of range (project has {len(project.playlists)} tracks)"
        )
    playlist = project.playlists[track]
    real_entries = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        return _err(
            f"clip_index {clip_index} out of range (track has {len(real_entries)} clips)"
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
        return _err(str(exc))

    seg_tuples = [(s.src_in, s.src_out, s.speed) for s in segments]
    src_frames, output_frames = sr.source_output_frames(segments)

    # Snapshot before mutating the project.
    try:
        snap = create_snapshot(ws_path, project_path, description="before_speed_ramp")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

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
        return _err(f"failed to apply speed ramp: {exc}")
    serialize_project(patched, project_path)

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "clip_index": clip_index,
        "playlist_id": playlist.id,
        "keyframe_format": kf_format,
        "easing": easing,
        "pitch_compensation": pitch_compensation,
        "segment_count": len(seg_tuples),
        "source_frames": src_frames,
        "expected_output_frames": output_frames,
        "expected_output_seconds": round(output_frames / fps, 3),
        "original_clip_frames": clip_frames,
        "snapshot_id": snapshot_id,
    })
