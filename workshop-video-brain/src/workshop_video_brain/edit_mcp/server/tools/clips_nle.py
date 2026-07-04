"""NLE clip/track editing operations.

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
    nonfinite_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    latest_project,
    _load_latest_project,
    _save_patched,
    _resolve_playlist,
)
from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames



@mcp.tool()
@tool_guard
def clip_insert(
    workspace_path: str,
    media_path: str,
    in_seconds: float = 0.0,
    out_seconds: float = -1.0,
    position: int = -1,
) -> dict:
    """Insert a clip into the timeline of the latest working copy project.

    Args:
        workspace_path: Path to workspace root.
        media_path: Path to the media file to insert.
        in_seconds: In-point in seconds (default: start of clip).
        out_seconds: Out-point in seconds (default: end of clip, -1 means full duration).
        position: Position index in the playlist (default: -1 = append at end).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        if not media_path or not media_path.strip():
            return invalid_input("media_path must be a non-empty string", "Pass the path to a media file (video/audio/image) to insert.", param="media_path")
        media_file = Path(media_path)
        if not media_file.exists():
            return missing_file(media_path, "media_path")
        if media_file.is_dir():
            return invalid_input(f"media_path is a directory, not a file: {media_path}", "Pass the path to a single media file, not a folder.", path=media_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return err("No .kdenlive files found in projects/working_copies/", error_type="missing_file", suggestion="Create a working copy first with project_create_working_copy, or verify this workspace has been initialised.")

        latest = latest_project(kdenlive_files)
        project = parse_project(latest)

        fps = project.profile.fps or 25.0

        # Probe media for duration using ffprobe if available
        duration_seconds: float | None = None
        try:
            import shutil
            if shutil.which("ffprobe"):
                import subprocess
                import json as _json
                probe_result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet",
                        "-print_format", "json",
                        "-show_streams",
                        str(media_file),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if probe_result.returncode == 0:
                    probe_data = _json.loads(probe_result.stdout)
                    for stream in probe_data.get("streams", []):
                        if stream.get("codec_type") == "video":
                            dur = stream.get("duration")
                            if dur:
                                duration_seconds = float(dur)
                                r_num = stream.get("r_frame_rate", "")
                                if "/" in r_num:
                                    num, den = r_num.split("/")
                                    if int(den) > 0:
                                        fps = int(num) / int(den)
                            break
                    if duration_seconds is None:
                        # fallback: check format
                        fmt = probe_data.get("format", {})
                        dur = fmt.get("duration")
                        if dur:
                            duration_seconds = float(dur)
        except Exception:
            pass  # ffprobe unavailable or failed; continue with defaults

        # Convert seconds to frames (half-up, canonical helper)
        in_frame = seconds_to_frames(in_seconds, fps)
        if out_seconds < 0:
            if duration_seconds is not None:
                out_frame = seconds_to_frames(duration_seconds, fps) - 1
            else:
                out_frame = in_frame  # fallback: single frame
        else:
            out_frame = seconds_to_frames(out_seconds, fps)

        # Find first video playlist to insert into
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}
        video_playlist = None
        for playlist in project.playlists:
            if playlist.id not in audio_playlist_ids:
                video_playlist = playlist
                break

        if video_playlist is None:
            return invalid_input("This project has no video track", "Add a working copy with at least one video track before inserting clips.")

        # Build a unique producer ID from the media filename
        import hashlib
        stem = media_file.stem
        h = hashlib.md5(str(media_file).encode()).hexdigest()[:6]
        producer_id = f"{stem}_{h}"

        intent = AddClip(
            producer_id=producer_id,
            track_ref=video_playlist.id,
            track_id=video_playlist.id,
            in_point=in_frame,
            out_point=out_frame,
            position=position,
            source_path=str(media_file),
        )

        patched, report = patch_project(project, [intent], with_report=True)
        if report.all_skipped:
            return err(
                "clip_insert applied no changes: "
                + "; ".join(s["reason"] for s in report.skipped),
                suggestion="Each reason above says why the insert was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "media_path": str(media_file),
            "producer_id": producer_id,
            "in_frame": in_frame,
            "out_frame": out_frame,
            "playlist_id": video_playlist.id,
            "position": position,
            "skipped_intents": report.skipped,
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Clip tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def clips_label(workspace_path: str) -> dict:
    """Auto-label all clips in workspace from transcript and marker data.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of labels generated and a summary of content types found.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.clip_labeler import generate_labels

        labels = generate_labels(ws_path)
        content_type_counts: dict[str, int] = {}
        for label in labels:
            content_type_counts[label.content_type] = (
                content_type_counts.get(label.content_type, 0) + 1
            )
        return _ok({
            "label_count": len(labels),
            "content_types": content_type_counts,
            "clips": [
                {
                    "clip_ref": l.clip_ref,
                    "content_type": l.content_type,
                    "shot_type": l.shot_type,
                    "has_speech": l.has_speech,
                    "speech_density": l.speech_density,
                    "topic_count": len(l.topics),
                    "duration": l.duration,
                }
                for l in labels
            ],
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clips_search(workspace_path: str, query: str) -> dict:
    """Search clips by content. Returns ranked matches.

    Args:
        workspace_path: Path to the workspace root directory.
        query: Search query string (case-insensitive).

    Returns:
        Ranked list of matching clips with scores.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        if not query or not query.strip():
            return invalid_input("query must be a non-empty string", "Pass a non-empty search term to match against clip content.", param="query")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.clip_search import search_clips

        results = search_clips(ws_path, query)
        return _ok({
            "results": results,
            "count": len(results),
            "query": query,
        })
    except Exception as exc:
        return from_exception(exc)


def _validate_clip_index(playlist, clip_index: int) -> list:
    """Return list of real entries, raising ValueError if clip_index out of range."""
    real = [e for e in playlist.entries if e.producer_id]
    if not real:
        raise ValueError(f"Playlist '{playlist.id}' has no clips")
    if clip_index < 0 or clip_index >= len(real):
        raise ValueError(
            f"clip_index {clip_index} out of range (playlist has {len(real)} clip(s))"
        )
    return real




# ---------------------------------------------------------------------------
# NLE clip operations
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def clip_remove(workspace_path: str, clip_index: int, track: int = 0) -> dict:
    """Remove a clip from the timeline by index.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to remove.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = RemoveClip(track_ref=playlist.id, clip_index=clip_index)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "removed_clip_index": clip_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_move(workspace_path: str, from_index: int, to_index: int, track: int = 0) -> dict:
    """Move a clip from one position to another on the timeline.

    Args:
        workspace_path: Path to workspace root.
        from_index: Source clip index.
        to_index: Destination clip index.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        real = _validate_clip_index(playlist, from_index)
        if to_index < 0 or to_index >= len(real):
            return invalid_index("to_index", to_index, f"0-{len(real) - 1}")

        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = MoveClip(track_ref=playlist.id, from_index=from_index, to_index=to_index)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "from_index": from_index,
            "to_index": to_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_split(workspace_path: str, clip_index: int, split_at_seconds: float = 0.0) -> dict:
    """Split a clip at a timestamp (razor tool).

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to split.
        split_at_seconds: Time offset within the clip (in seconds) to split at.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)
        # clip_split operates on the first video playlist
        playlist = _resolve_playlist(project, 0)
        real = _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        split_at_frame = seconds_to_frames(split_at_seconds, fps)

        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SplitClip(
            track_ref=playlist.id,
            clip_index=clip_index,
            split_at_frame=split_at_frame,
        )
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "split_at_seconds": split_at_seconds,
            "split_at_frame": split_at_frame,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_trim(
    workspace_path: str,
    clip_index: int,
    in_seconds: float = -1,
    out_seconds: float = -1,
) -> dict:
    """Trim a clip's in and/or out points.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to trim.
        in_seconds: New in-point in seconds (-1 = leave unchanged).
        out_seconds: New out-point in seconds (-1 = leave unchanged).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, 0)
        _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        new_in = seconds_to_frames(in_seconds, fps) if in_seconds >= 0 else -1
        new_out = seconds_to_frames(out_seconds, fps) if out_seconds >= 0 else -1

        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        clip_ref = f"{playlist.id}:{clip_index}"
        intent = TrimClip(clip_ref=clip_ref, new_in=new_in, new_out=new_out)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "new_in_frame": new_in,
            "new_out_frame": new_out,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_ripple_delete(workspace_path: str, clip_index: int, track: int = 0) -> dict:
    """Remove a clip and close the gap.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to delete.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import RippleDelete
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = RippleDelete(track_ref=playlist.id, clip_index=clip_index)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "deleted_clip_index": clip_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_speed(
    workspace_path: str,
    clip_index: int,
    speed: float = 1.0,
    track: int = 0,
) -> dict:
    """Change clip playback speed (0.5=slow, 2.0=fast).

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip.
        speed: Playback speed multiplier (must be > 0).
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        nf = nonfinite_guard(speed=speed)
        if nf is not None:
            return nf
        if speed <= 0:
            return invalid_input(f"speed must be greater than 0, got: {speed}", "Pass a positive multiplier: 0.5 = half speed, 2.0 = double speed.", param="speed", given=speed)
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import SetClipSpeed
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetClipSpeed(track_ref=playlist.id, clip_index=clip_index, speed=speed)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "speed": speed,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_fade(
    workspace_path: str,
    clip_index: int,
    fade_type: str = "in",
    duration_seconds: float = 1.0,
    track: int = 0,
) -> dict:
    """Apply audio fade in or out to a clip.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip.
        fade_type: "in" or "out".
        duration_seconds: Duration of the fade in seconds.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        if fade_type not in ("in", "out"):
            return invalid_input(f"fade_type must be 'in' or 'out', got: {fade_type!r}", "Pass fade_type='in' or fade_type='out'.", param="fade_type", given=fade_type)
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        duration_frames = max(1, seconds_to_frames(duration_seconds, fps))

        from workshop_video_brain.core.models.timeline import AudioFade as AudioFadeIntent
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = AudioFadeIntent(
            track_ref=playlist.id,
            clip_index=clip_index,
            fade_type=fade_type,
            duration_frames=duration_frames,
        )
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "fade_type": fade_type,
            "duration_seconds": duration_seconds,
            "duration_frames": duration_frames,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def track_add(workspace_path: str, track_type: str = "video", name: str = "") -> dict:
    """Add a new video or audio track to the project.

    Args:
        workspace_path: Path to workspace root.
        track_type: "video" or "audio".
        name: Optional name for the new track.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        if track_type not in ("video", "audio"):
            return invalid_input(f"track_type must be 'video' or 'audio', got: {track_type!r}", "Pass track_type='video' or track_type='audio'.", param="track_type", given=track_type)
        ws_path, project, latest = _load_latest_project(workspace_path)

        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = CreateTrack(track_type=track_type, name=name)
        patched = patch_project(project, [intent])
        # Find the newly added playlist (last one)
        new_playlist_id = patched.playlists[-1].id if patched.playlists else ""
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_type": track_type,
            "name": name,
            "new_playlist_id": new_playlist_id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def track_mute(workspace_path: str, track_index: int, muted: bool = True) -> dict:
    """Mute or unmute a track.

    Args:
        workspace_path: Path to workspace root.
        track_index: Zero-based index into all project tracks.
        muted: True to mute, False to unmute.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)

        if track_index < 0 or track_index >= len(project.tracks):
            return invalid_index("track_index", track_index, f"0-{len(project.tracks) - 1}")

        track = project.tracks[track_index]

        from workshop_video_brain.core.models.timeline import SetTrackMute
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetTrackMute(track_ref=track.id, muted=muted)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_index": track_index,
            "track_id": track.id,
            "muted": muted,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def track_visibility(workspace_path: str, track_index: int, visible: bool = True) -> dict:
    """Show or hide a video track.

    Args:
        workspace_path: Path to workspace root.
        track_index: Zero-based index into all project tracks.
        visible: True to show, False to hide.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path, project, latest = _load_latest_project(workspace_path)

        if track_index < 0 or track_index >= len(project.tracks):
            return invalid_index("track_index", track_index, f"0-{len(project.tracks) - 1}")

        track = project.tracks[track_index]

        from workshop_video_brain.core.models.timeline import SetTrackVisibility
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetTrackVisibility(track_ref=track.id, visible=visible)
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_index": track_index,
            "track_id": track.id,
            "visible": visible,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def gap_insert(
    workspace_path: str,
    position: int,
    duration_seconds: float,
    track: int = 0,
) -> dict:
    """Insert a gap/blank at a position on the timeline.

    Args:
        workspace_path: Path to workspace root.
        position: Playlist entry index at which to insert the gap.
        duration_seconds: Duration of the gap in seconds.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        nf = nonfinite_guard(duration_seconds=duration_seconds)
        if nf is not None:
            return nf
        if duration_seconds <= 0:
            return invalid_input(f"duration_seconds must be positive, got: {duration_seconds}", "Pass a positive gap duration in seconds (e.g. 1.5).", param="duration_seconds", given=duration_seconds)
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)

        fps = project.profile.fps or 25.0
        duration_frames = max(1, seconds_to_frames(duration_seconds, fps))

        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = InsertGap(
            track_id=playlist.id,
            position=position,
            duration_frames=duration_frames,
        )
        patched, _report = patch_project(project, [intent], with_report=True)
        if _report.all_skipped:
            return err(
                "no changes applied: "
                + "; ".join(s["reason"] for s in _report.skipped),
                suggestion="Each reason above says why an edit was skipped. Fix the offending track/clip index or timing (project_summary shows what the project actually contains) and retry.",
            )
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "position": position,
            "duration_seconds": duration_seconds,
            "duration_frames": duration_frames,
            "playlist_id": playlist.id,
            "skipped_intents": _report.skipped,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)
