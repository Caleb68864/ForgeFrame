"""Slip, slide, replace and ripple-insert trims on the latest working copy.

Thin shells over the ``SlipClip`` / ``SlideClip`` / ``ReplaceClip`` /
``RippleInsert`` intents (math in ``pipelines/trim_ops``). ``track`` is the
video-track index (0 = first video track), as ``clip_trim`` takes it. Each
trim is applied to the clip's linked audio entry too; ``audio_synced`` says
whether there was one.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    from_exception,
    invalid_index,
    invalid_input,
    missing_file,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

_FALLBACK = "Check the clip index with project_summary, then retry."


def _load(workspace_path: str, track: int):
    from workshop_video_brain.edit_mcp.server.tools_helpers import (
        _get_video_playlists,
        _load_latest_project,
    )

    ws_path, project, latest = _load_latest_project(workspace_path)
    videos = _get_video_playlists(project)
    if track < 0 or track >= len(videos):
        return None, invalid_index("track", track, f"0-{len(videos) - 1}" if videos else "none")
    return (ws_path, project, latest, videos[track]), None


def _clip_or_error(playlist, clip_index: int):
    real = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real):
        return None, invalid_index("clip", clip_index, f"0-{len(real) - 1}" if real else "none")
    return real[clip_index], None


def _media_path(project, producer_id: str) -> Path | None:
    producer = next((p for p in project.producers if p.id == producer_id), None)
    if producer is None:
        return None
    resource = producer.properties.get("resource") or producer.resource
    if producer.properties.get("mlt_service") in ("color", "colour") or not resource:
        return None
    path = Path(resource)
    return path if path.is_file() else None


def _source_frames(project, producer_id: str, fps: float) -> int | None:
    """Frames of source media: probed for a file, the ``length`` property otherwise."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_duration_seconds
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

    path = _media_path(project, producer_id)
    if path is not None:
        seconds = probe_duration_seconds(path)
        if seconds:
            return seconds_to_frames(seconds, fps)
    producer = next((p for p in project.producers if p.id == producer_id), None)
    try:
        return int(producer.properties["length"]) if producer else None
    except (KeyError, ValueError):
        return None


def _has_audio(project, producer_id: str, media: Path | None) -> bool:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import count_audio_streams

    path = media or _media_path(project, producer_id)
    if path is None:
        return False
    try:
        return count_audio_streams(path) > 0
    except Exception:  # noqa: BLE001 -- unprobeable: treat as silent
        return False


def _patch_and_save(ws_path, project, workspace_path: str, intents: list):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.server.tools_helpers import _save_patched

    patched, report = patch_project(project, intents, with_report=True)
    if report.all_skipped:
        return None, None, invalid_input(
            "no changes applied: " + "; ".join(s["reason"] for s in report.skipped), _FALLBACK)
    return patched, _save_patched(ws_path, patched, workspace_path), None


def _clip_report(project, playlist_id: str, clip_index: int) -> dict:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_trims import find_linked_audio
    from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_at_index, clip_start_frame, playlist_length

    playlist = next(pl for pl in project.playlists if pl.id == playlist_id)
    clip = clip_at_index(playlist.entries, clip_index)
    start = clip_start_frame(playlist.entries, clip_index)
    linked = find_linked_audio(project, playlist, clip_index)
    synced = False
    if linked:
        a_clip = clip_at_index(linked[0].entries, linked[1])
        synced = (clip_start_frame(linked[0].entries, linked[1]) == start
                  and (a_clip.in_point, a_clip.out_point) == (clip.in_point, clip.out_point))
    return {"clip_index": clip_index, "producer_id": clip.producer_id, "in_frame": clip.in_point,
            "out_frame": clip.out_point, "start_frame": start, "audio_synced": synced,
            "track_frames": playlist_length(playlist.entries)}


def _neighbour_frames(project, playlist, clip_index: int, fps: float):
    """Source frames of the clips directly before/after (None for blanks or unknown)."""
    entries = playlist.entries
    real = -1
    for i, entry in enumerate(entries):
        if entry.producer_id:
            real += 1
            if real == clip_index:
                prev = entries[i - 1] if i > 0 else None
                nxt = entries[i + 1] if i + 1 < len(entries) else None
                frames = lambda e: _source_frames(project, e.producer_id, fps) if e and e.producer_id else None  # noqa: E731
                return frames(prev), frames(nxt)
    return None, None


@mcp.tool()
@tool_guard
def clip_slip(workspace_path: str, clip_index: int, offset_seconds: float, track: int = 0) -> dict:
    """Slip a clip: show a later (offset > 0) or earlier part of its source, same place and length.

    The linked audio slips by the same amount. Refused past the start or end of
    the source, and for speed-changed clips.
    """
    from workshop_video_brain.core.models.timeline import SlipClip
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

    try:
        loaded, problem = _load(workspace_path, track)
        if problem:
            return problem
        ws_path, project, _latest, playlist = loaded
        clip, problem = _clip_or_error(playlist, clip_index)
        if problem:
            return problem
        fps = project.profile.fps or 25.0
        delta = (1 if offset_seconds >= 0 else -1) * seconds_to_frames(abs(offset_seconds), fps)
        if delta == 0:
            return invalid_input("offset_seconds rounds to 0 frames", "Pass a non-zero offset of at least one frame.")
        before = _clip_report(project, playlist.id, clip_index)
        patched, out_path, problem = _patch_and_save(ws_path, project, workspace_path, [SlipClip(
            track_ref=playlist.id, clip_index=clip_index, delta_frames=delta,
            source_frames=_source_frames(project, clip.producer_id, fps))])
        if problem:
            return problem
        return _ok({"kdenlive_path": str(out_path), "delta_frames": delta, "before": before,
                    "after": _clip_report(patched, playlist.id, clip_index)})
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_slide(workspace_path: str, clip_index: int, offset_seconds: float, track: int = 0) -> dict:
    """Slide a clip later (offset > 0) or earlier along its track; its neighbours absorb the move.

    The clip shows the same frames; the clip (or gap) before it grows and the
    one after it shrinks (or the reverse). The linked audio slides with it.
    """
    from workshop_video_brain.core.models.timeline import SlideClip
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

    try:
        loaded, problem = _load(workspace_path, track)
        if problem:
            return problem
        ws_path, project, _latest, playlist = loaded
        _clip, problem = _clip_or_error(playlist, clip_index)
        if problem:
            return problem
        fps = project.profile.fps or 25.0
        delta = (1 if offset_seconds >= 0 else -1) * seconds_to_frames(abs(offset_seconds), fps)
        if delta == 0:
            return invalid_input("offset_seconds rounds to 0 frames", "Pass a non-zero offset of at least one frame.")
        prev_frames, next_frames = _neighbour_frames(project, playlist, clip_index, fps)
        before = _clip_report(project, playlist.id, clip_index)
        patched, out_path, problem = _patch_and_save(ws_path, project, workspace_path, [SlideClip(
            track_ref=playlist.id, clip_index=clip_index, delta_frames=delta,
            prev_source_frames=prev_frames, next_source_frames=next_frames)])
        if problem:
            return problem
        return _ok({"kdenlive_path": str(out_path), "delta_frames": delta, "before": before,
                    "after": _clip_report(patched, playlist.id, clip_index)})
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_replace(
    workspace_path: str,
    clip_index: int,
    source: str,
    source_in_seconds: float = 0.0,
    track: int = 0,
    replace_audio: bool = True,
) -> dict:
    """Replace a clip's media, keeping its place and length.

    ``source`` is a media path or an existing producer id. With
    ``replace_audio`` the linked audio switches too (or becomes silence when
    the new media has none); without it the old sound stays under the new picture.
    """
    from workshop_video_brain.core.models.timeline import ReplaceClip
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames
    from workshop_video_brain.edit_mcp.server.bundles.clip_place import _resolve_source

    try:
        loaded, problem = _load(workspace_path, track)
        if problem:
            return problem
        ws_path, project, _latest, playlist = loaded
        _clip, problem = _clip_or_error(playlist, clip_index)
        if problem:
            return problem
        if not source or not source.strip():
            return invalid_input("source must be a media path or producer id", "Pass the replacement media.")
        producer_id, source_path, _duration = _resolve_source(project, source.strip(), ws_path)
        if source_path and not Path(source_path).exists():
            return missing_file(source_path, "source media")
        fps = project.profile.fps or 25.0
        media = Path(source_path) if source_path else None
        if media is not None:
            from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_duration_seconds
            seconds = probe_duration_seconds(media)
            frames = seconds_to_frames(seconds, fps) if seconds else None
        else:
            frames = _source_frames(project, producer_id, fps)
        before = _clip_report(project, playlist.id, clip_index)
        patched, out_path, problem = _patch_and_save(ws_path, project, workspace_path, [ReplaceClip(
            track_ref=playlist.id, clip_index=clip_index, producer_id=producer_id,
            source_path=source_path, new_in=seconds_to_frames(source_in_seconds, fps),
            source_frames=frames, replace_audio=replace_audio,
            new_has_audio=_has_audio(project, producer_id, media))])
        if problem:
            return problem
        return _ok({"kdenlive_path": str(out_path), "before": before,
                    "after": _clip_report(patched, playlist.id, clip_index)})
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def clip_ripple_insert(
    workspace_path: str,
    source: str,
    before_clip_index: int,
    in_seconds: float = 0.0,
    out_seconds: float = -1.0,
    track: int = 0,
    ripple_all_tracks: bool = True,
) -> dict:
    """Insert a clip and its audio before ``before_clip_index``; everything after moves right.

    ``before_clip_index`` equal to the number of clips appends at the end.
    ``out_seconds`` -1 uses the whole source. With ``ripple_all_tracks`` every
    other track, guide and later transition moves too, keeping the timeline in sync.
    """
    from workshop_video_brain.core.models.timeline import RippleInsert
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames
    from workshop_video_brain.edit_mcp.server.bundles.clip_place import _resolve_source

    try:
        loaded, problem = _load(workspace_path, track)
        if problem:
            return problem
        ws_path, project, _latest, playlist = loaded
        real = sum(1 for e in playlist.entries if e.producer_id)
        if before_clip_index < 0 or before_clip_index > real:
            return invalid_index("clip", before_clip_index, f"0-{real}")
        if not source or not source.strip():
            return invalid_input("source must be a media path or producer id", "Pass the media to insert.")
        producer_id, source_path, duration = _resolve_source(project, source.strip(), ws_path)
        if source_path and not Path(source_path).exists():
            return missing_file(source_path, "source media")
        fps = project.profile.fps or 25.0
        in_point = seconds_to_frames(in_seconds, fps)
        if out_seconds is not None and out_seconds >= 0:
            out_point = seconds_to_frames(out_seconds, fps) - 1
        else:
            total = seconds_to_frames(duration, fps) if duration else _source_frames(project, producer_id, fps)
            if not total:
                return invalid_input("The source length is unknown", "Pass out_seconds explicitly.")
            out_point = total - 1
        if out_point < in_point:
            return invalid_input(f"out frame {out_point} is before in frame {in_point}",
                                 "out_seconds must be greater than in_seconds.")
        media = Path(source_path) if source_path else None
        before_len = sum(e.out_point - e.in_point + 1 for e in playlist.entries)
        patched, out_path, problem = _patch_and_save(ws_path, project, workspace_path, [RippleInsert(
            track_ref=playlist.id, before_clip_index=before_clip_index, producer_id=producer_id,
            source_path=source_path, in_point=in_point, out_point=out_point,
            with_audio=_has_audio(project, producer_id, media), ripple_all_tracks=ripple_all_tracks)])
        if problem:
            return problem
        after = _clip_report(patched, playlist.id, before_clip_index)
        return _ok({"kdenlive_path": str(out_path), "inserted": after,
                    "length_frames": out_point - in_point + 1,
                    "track_frames_before": before_len, "track_frames_after": after["track_frames"]})
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
