"""Timeline transition tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    latest_project,
)





# ---------------------------------------------------------------------------
# Transitions tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def transitions_apply(
    workspace_path: str,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply transitions to the latest working copy project.

    Args:
        workspace_path: Path to the workspace root directory.
        transition_type: Type of transition, e.g. "crossfade".
        preset: Duration preset: "short", "medium", or "long".

    Returns:
        Path to the updated .kdenlive file.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset, TransitionType
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.core.utils.naming import slugify
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return err("No .kdenlive files found in projects/working_copies/", error_type="missing_file", suggestion="Create a working copy first with project_create_working_copy, or verify this workspace has been initialised.")

        latest = latest_project(kdenlive_files)
        project = parse_project(latest)

        try:
            t_preset = TransitionPreset(preset)
        except ValueError:
            t_preset = TransitionPreset.medium

        # Identify audio playlist IDs from tracks
        audio_playlist_ids = {
            t.id for t in project.tracks if t.track_type == "audio"
        }

        intents = []
        # Apply a transition between each adjacent pair of video playlist entries
        for playlist in project.playlists:
            if playlist.id in audio_playlist_ids:
                continue
            entries = [e for e in playlist.entries if e.producer_id]
            for i in range(len(entries) - 1):
                left = entries[i]
                right = entries[i + 1]
                intents.append(
                    AddTransition(
                        type=transition_type,
                        track_ref=playlist.id,
                        left_clip_ref=left.producer_id,
                        right_clip_ref=right.producer_id,
                        duration_frames=t_preset.frames,
                    )
                )

        patched, report = patch_project(
            project,
            intents,
            workspace_root=ws_path,
            project_path=latest,
            with_report=True,
        )
        if report.all_skipped:
            return _err(
                "transitions_apply applied no changes: "
                + "; ".join(s["reason"] for s in report.skipped)
            )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transitions_applied": len(report.applied),
            "transition_type": transition_type,
            "preset": preset,
            "skipped_intents": report.skipped,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def transitions_apply_at(
    workspace_path: str,
    timestamp_seconds: float,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply a transition at a specific timestamp in the timeline.

    Finds the cut point closest to the given timestamp and applies
    a transition between those two clips.

    Args:
        workspace_path: Path to workspace root.
        timestamp_seconds: Time in seconds where the transition should go.
        transition_type: Type (crossfade, dissolve, fade_in, fade_out).
        preset: Duration (short=12f, medium=24f, long=48f).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        if timestamp_seconds < 0:
            return _err("timestamp_seconds must be >= 0")

        _KNOWN_TRANSITION_TYPES = {"crossfade", "dissolve", "fade_in", "fade_out"}
        if transition_type not in _KNOWN_TRANSITION_TYPES:
            return _err(
                f"Unknown transition_type '{transition_type}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_TRANSITION_TYPES))}"
            )
        _KNOWN_PRESETS = {"short", "medium", "long"}
        if preset not in _KNOWN_PRESETS:
            return _err(
                f"Unknown preset '{preset}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_PRESETS))}"
            )

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return err("No .kdenlive files found in projects/working_copies/", error_type="missing_file", suggestion="Create a working copy first with project_create_working_copy, or verify this workspace has been initialised.")

        latest = latest_project(kdenlive_files)
        project = parse_project(latest)

        fps = project.profile.fps or 25.0
        target_frame = int(timestamp_seconds * fps)
        tolerance_frames = int(2.0 * fps)  # 2-second tolerance

        # Identify audio playlist IDs
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}

        # Find the closest cut boundary across all video playlists
        best_distance = None
        best_playlist_id = None
        best_left = None
        best_right = None

        for playlist in project.playlists:
            if playlist.id in audio_playlist_ids:
                continue
            entries = [e for e in playlist.entries if e.producer_id]
            # Calculate cumulative frame positions for each entry boundary
            current_frame = 0
            for i, entry in enumerate(entries):
                duration = entry.out_point - entry.in_point + 1
                boundary_frame = current_frame + duration  # frame where this entry ends
                if i < len(entries) - 1:
                    # There's a next entry — this is a cut point
                    dist = abs(boundary_frame - target_frame)
                    if best_distance is None or dist < best_distance:
                        best_distance = dist
                        best_playlist_id = playlist.id
                        best_left = entries[i]
                        best_right = entries[i + 1]
                current_frame += duration

        if best_distance is None or best_distance > tolerance_frames:
            return _err(f"No cut point found near {timestamp_seconds}s")

        t_preset = TransitionPreset(preset)
        intents = [
            AddTransition(
                type=transition_type,
                track_ref=best_playlist_id,
                left_clip_ref=best_left.producer_id,
                right_clip_ref=best_right.producer_id,
                duration_frames=t_preset.frames,
            )
        ]

        patched, report = patch_project(
            project, intents, workspace_root=ws_path, project_path=latest,
            with_report=True,
        )
        if report.all_skipped:
            return _err(
                "transitions_apply_at applied no changes: "
                + "; ".join(s["reason"] for s in report.skipped)
            )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transition_type": transition_type,
            "preset": preset,
            "timestamp_seconds": timestamp_seconds,
            "boundary_frame": int(target_frame + best_distance if best_left else target_frame),
            "playlist_id": best_playlist_id,
            "skipped_intents": report.skipped,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def transitions_apply_between(
    workspace_path: str,
    clip_index: int,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply a transition between clip N and clip N+1 on the first video track.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the left clip. Transition goes between this and the next.
        transition_type: Type (crossfade, dissolve, fade_in, fade_out).
        preset: Duration (short, medium, long).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        if clip_index < 0:
            return _err("clip_index must be >= 0")

        _KNOWN_TRANSITION_TYPES = {"crossfade", "dissolve", "fade_in", "fade_out"}
        if transition_type not in _KNOWN_TRANSITION_TYPES:
            return _err(
                f"Unknown transition_type '{transition_type}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_TRANSITION_TYPES))}"
            )
        _KNOWN_PRESETS = {"short", "medium", "long"}
        if preset not in _KNOWN_PRESETS:
            return _err(
                f"Unknown preset '{preset}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_PRESETS))}"
            )

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return err("No .kdenlive files found in projects/working_copies/", error_type="missing_file", suggestion="Create a working copy first with project_create_working_copy, or verify this workspace has been initialised.")

        latest = latest_project(kdenlive_files)
        project = parse_project(latest)

        # Find first video playlist
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}
        video_playlist = None
        for playlist in project.playlists:
            if playlist.id not in audio_playlist_ids:
                video_playlist = playlist
                break

        if video_playlist is None:
            return _err("No video playlist found in project")

        entries = [e for e in video_playlist.entries if e.producer_id]
        if len(entries) < 2:
            return _err("Video playlist has fewer than 2 clips; no transition possible")

        if clip_index >= len(entries) - 1:
            return _err(
                f"clip_index {clip_index} is out of range. "
                f"Valid range is 0 to {len(entries) - 2} (playlist has {len(entries)} clips)."
            )

        left = entries[clip_index]
        right = entries[clip_index + 1]

        t_preset = TransitionPreset(preset)
        intents = [
            AddTransition(
                type=transition_type,
                track_ref=video_playlist.id,
                left_clip_ref=left.producer_id,
                right_clip_ref=right.producer_id,
                duration_frames=t_preset.frames,
            )
        ]

        patched, report = patch_project(
            project, intents, workspace_root=ws_path, project_path=latest,
            with_report=True,
        )
        if report.all_skipped:
            return _err(
                "transitions_apply_between applied no changes: "
                + "; ".join(s["reason"] for s in report.skipped)
            )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transition_type": transition_type,
            "preset": preset,
            "clip_index": clip_index,
            "left_clip": left.producer_id,
            "right_clip": right.producer_id,
            "playlist_id": video_playlist.id,
            "skipped_intents": report.skipped,
        })
    except Exception as exc:
        return from_exception(exc)
