"""Cut, zoom and flash on the beat, from ``music_beat_grid``'s beat file.

Three tools on the latest working copy. Beats are chosen with musical variety
(``intensity``: subtle = every 4th beat, medium = every 2nd, aggressive = every
beat; bar beats always kept), mapped to timeline frames through the music
clip's position and in-point (or ``music_offset_seconds``), then:
``beat_cut`` moves cuts onto beats (out-points only, linked audio too),
``beat_zoom`` adds one zoom-punch ``qtblend`` per hit clip, ``beat_flash`` one
keyframed ``brightness`` per hit clip. Maths in ``pipelines/beat_sync``.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    from_exception,
    invalid_index,
    invalid_input,
    missing_file,
    not_found,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

_GRID_HINT = "Run music_beat_grid on the music first; it writes reports/beat_grid.json."


class _Problem(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload.get("message", ""))
        self.payload = payload


def _read_grid(ws_path: Path, beat_file: str) -> dict:
    path = Path(beat_file) if beat_file else ws_path / "reports" / "beat_grid.json"
    if not path.is_absolute():
        path = ws_path / path
    if not path.is_file():
        raise _Problem(missing_file(str(path), "beat grid"))
    try:
        grid = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _Problem(invalid_input(f"Beat grid is not valid JSON: {exc}", _GRID_HINT, path=str(path))) from exc
    if not grid.get("beats"):
        raise _Problem(not_found("Beats", str(path), hint="The grid has no beats. " + _GRID_HINT))
    grid["_path"] = str(path)
    return grid


def _same_file(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def _beat_frames(project, ws_path: Path, grid: dict, selected: list[float], music_track: int,
                 music_clip_index: int, music_offset_seconds: float) -> tuple[list[int], int, dict]:
    """Timeline frames of the selected beats, beats skipped, and how the music was located."""
    from workshop_video_brain.edit_mcp.pipelines.beat_sync import beats_to_timeline_frames
    from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_at_index, clip_start_frame

    fps = project.profile.fps or 25.0
    if music_offset_seconds is not None and music_offset_seconds >= 0:
        frames, skipped = beats_to_timeline_frames(selected, fps, offset_seconds=music_offset_seconds)
        return frames, skipped, {"music": "offset", "offset_seconds": music_offset_seconds}
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    audio_playlists = [p for p in project.playlists if p.id in audio_ids]
    entry = start = None
    if music_track >= 0:
        if music_track >= len(audio_playlists):
            raise _Problem(invalid_index("music_track", music_track, f"0-{len(audio_playlists) - 1}"))
        playlist = audio_playlists[music_track]
        try:
            entry = clip_at_index(playlist.entries, music_clip_index)
            start = clip_start_frame(playlist.entries, music_clip_index)
        except IndexError:
            raise _Problem(invalid_index("music_clip_index", music_clip_index, "a clip on that audio track")) from None
    else:
        source = grid.get("source", "")
        producers = {p.id: (p.properties.get("resource") or p.resource) for p in project.producers}
        for playlist in audio_playlists:
            real = [e for e in playlist.entries if e.producer_id]
            for index, candidate in enumerate(real):
                resource = producers.get(candidate.producer_id, "")
                if source and resource and _same_file(resource, source):
                    entry, start = candidate, clip_start_frame(playlist.entries, index)
                    break
            if entry is not None:
                break
    if entry is None:
        raise _Problem(invalid_input(
            "Could not find the music on the timeline",
            "Either put the analysed music on an audio track (it is found by file), name it with "
            "music_track + music_clip_index, or pass music_offset_seconds (the timeline time where "
            "the music starts from its beginning).", source=grid.get("source", "")))
    frames, skipped = beats_to_timeline_frames(selected, fps, start, entry.in_point, entry.out_point)
    return frames, skipped, {"music": "entry", "music_start_frame": start, "music_in_frame": entry.in_point}


def _prepare(workspace_path, track, beat_file, intensity, every_n, phase, music_track, music_clip_index,
             music_offset_seconds):
    from workshop_video_brain.edit_mcp.pipelines.beat_sync import select_beats
    from workshop_video_brain.edit_mcp.server.tools_helpers import _get_video_playlists, _load_latest_project

    ws_path, project, latest = _load_latest_project(workspace_path)
    videos = _get_video_playlists(project)
    if track < 0 or track >= len(videos):
        raise _Problem(invalid_index("track", track, f"0-{len(videos) - 1}" if videos else "none"))
    grid = _read_grid(ws_path, beat_file)
    try:
        selected = select_beats(grid["beats"], intensity=intensity, every_n=every_n, phase=phase)
    except ValueError as exc:
        raise _Problem(invalid_input(str(exc), "intensity is subtle, medium or aggressive; or pass every_n.")) from exc
    frames, skipped, music = _beat_frames(project, ws_path, grid, selected, music_track, music_clip_index,
                                          music_offset_seconds)
    return ws_path, project, videos[track], grid, selected, frames, skipped, music


def _records(playlist) -> list[dict]:
    from workshop_video_brain.edit_mcp.pipelines.clip_place import entry_length

    out, start, index = [], 0, 0
    for entry in playlist.entries:
        length = entry_length(entry)
        if entry.producer_id:
            out.append({"clip_index": index, "start": start, "length": length, "in": entry.in_point,
                        "producer_id": entry.producer_id})
            index += 1
        start += length
    return out


def _common(grid, selected, frames, skipped, music, out_path):
    return {"bpm": grid.get("bpm_estimate"), "beat_file": grid["_path"], "selected_beats": selected,
            "beat_frames": frames, "beats_skipped_outside_music": skipped, **music,
            "kdenlive_path": str(out_path)}


@mcp.tool()
@tool_guard
def beat_cut(
    workspace_path: str,
    track: int = 0,
    first_clip_index: int = 0,
    last_clip_index: int = -1,
    beat_file: str = "",
    intensity: str = "medium",
    every_n: int = 0,
    phase: int = 0,
    music_track: int = -1,
    music_clip_index: int = 0,
    music_offset_seconds: float = -1.0,
    min_clip_seconds: float = 0.25,
) -> dict:
    """Re-time consecutive clips so each cut lands on a selected beat.

    Clips ``first_clip_index``..``last_clip_index`` (-1 = last) keep their order
    and the first keeps its start; each following cut moves to the next
    selected beat at least ``min_clip_seconds`` on. Only out-points change (and
    the same on each clip's linked audio); a clip without enough source stops
    short and is flagged ``off_beat``. Everything after the last clip shifts
    by the total change.
    """
    from workshop_video_brain.core.models.timeline import TrimClip
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher_trims import (
        ensure_producer_length,
        find_linked_audio,
    )
    from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames
    from workshop_video_brain.edit_mcp.pipelines.beat_sync import plan_beat_cut
    from workshop_video_brain.edit_mcp.server.bundles.clip_trims import _source_frames
    from workshop_video_brain.edit_mcp.server.tools_helpers import _save_patched

    try:
        ws_path, project, playlist, grid, selected, frames, skipped, music = _prepare(
            workspace_path, track, beat_file, intensity, every_n, phase, music_track, music_clip_index,
            music_offset_seconds)
        records = _records(playlist)
        last = len(records) - 1 if last_clip_index < 0 else last_clip_index
        if not (0 <= first_clip_index <= last < len(records)):
            return invalid_index("clip", first_clip_index if first_clip_index > last or first_clip_index < 0 else last,
                                 f"0-{len(records) - 1}" if records else "none")
        fps = project.profile.fps or 25.0
        chosen = records[first_clip_index:last + 1]
        for k, record in enumerate(chosen):
            record["source_frames"] = _source_frames(project, record["producer_id"], fps)
            if k:
                prev = chosen[k - 1]
                record["gap_before"] = record["start"] - (prev["start"] + prev["length"])
        plan = plan_beat_cut(chosen, frames, min_clip_frames=max(1, seconds_to_frames(min_clip_seconds, fps)))
        intents, linked_count = [], 0
        for record, step in zip(chosen, plan):
            if step["new_length"] == record["length"]:
                continue
            new_out = record["in"] + step["new_length"] - 1
            intents.append(TrimClip(clip_ref=f"{playlist.id}:{record['clip_index']}", new_in=-1, new_out=new_out))
            linked = find_linked_audio(project, playlist, record["clip_index"])
            if linked:
                linked_count += 1
                intents.append(TrimClip(clip_ref=f"{linked[0].id}:{linked[1]}", new_in=-1, new_out=new_out))
        if not intents:
            return invalid_input("No cut moved: every boundary is already on a selected beat or no beat is in reach",
                                 "Try intensity='aggressive' or every_n=1, or check the music position.")
        patched = patch_project(project, intents)
        for record in chosen:
            ensure_producer_length(patched, record["producer_id"])
        out_path = _save_patched(ws_path, patched, workspace_path)
        clips = [{"clip_index": r["clip_index"], "old_length": s["old_length"], "new_length": s["new_length"],
                  "cut_frame": s["cut_frame"], "off_beat": s["off_beat"]} for r, s in zip(chosen, plan)]
        shift = sum(c["new_length"] - c["old_length"] for c in clips)
        return _ok({**_common(grid, selected, frames, skipped, music, out_path), "clips": clips,
                    "linked_audio_trimmed": linked_count, "shift_after_last_clip_frames": shift})
    except _Problem as problem:
        return problem.payload
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


def _pulse_tool(kind: str, workspace_path, track, beat_file, intensity, every_n, phase, music_track,
                music_clip_index, music_offset_seconds, **params) -> dict:
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.pipelines import beat_sync, camera_moves
    from workshop_video_brain.edit_mcp.pipelines.keyframes import build_keyframe_string
    from workshop_video_brain.edit_mcp.server.tools import _build_filter_xml
    from workshop_video_brain.edit_mcp.server.tools_helpers import _save_patched

    try:
        ws_path, project, playlist, grid, selected, frames, skipped, music = _prepare(
            workspace_path, track, beat_file, intensity, every_n, phase, music_track, music_clip_index,
            music_offset_seconds)
        records = _records(playlist)
        hits, over_blanks = beat_sync.clip_hits(records, frames)
        if not hits:
            return invalid_input("No selected beat falls on a clip of this track",
                                 "Check the music position (music_offset_seconds) and the track.")
        fps = project.profile.fps or 25.0
        track_index = project.playlists.index(playlist)
        added = []
        for clip_index, local in sorted(hits.items()):
            length = records[clip_index]["length"]
            if kind == "zoom":
                result = camera_moves.zoom_punch_train(project.profile.width, project.profile.height, local, fps,
                                                       length, intensity=params["punch"],
                                                       attack_frames=params["attack_frames"],
                                                       decay_frames=params["decay_frames"])
                xml = _build_filter_xml(mlt_service="qtblend", kdenlive_id="qtblend", track=track_index,
                                        clip=clip_index, props=[("rect", result["rect"])])
            else:
                kfs = beat_sync.flash_keyframes(local, length, strength=params["strength"],
                                                decay_frames=params["decay_frames"])
                xml = _build_filter_xml(mlt_service="brightness", kdenlive_id="brightness", track=track_index,
                                        clip=clip_index, props=[("level", build_keyframe_string("scalar", kfs, fps))])
            position = len(patcher.list_effects(project, (track_index, clip_index)))
            patcher.insert_effect_xml(project, (track_index, clip_index), xml, position=position)
            added.append({"clip_index": clip_index, "beats": len(local), "effect_index": position})
        out_path = _save_patched(ws_path, project, workspace_path)
        return _ok({**_common(grid, selected, frames, skipped, music, out_path), "clips": added,
                    "beats_over_blanks": over_blanks})
    except _Problem as problem:
        return problem.payload
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def beat_zoom(
    workspace_path: str,
    track: int = 0,
    beat_file: str = "",
    intensity: str = "medium",
    every_n: int = 0,
    phase: int = 0,
    punch: float = 0.12,
    attack_frames: int = 2,
    decay_frames: int = 8,
    music_track: int = -1,
    music_clip_index: int = 0,
    music_offset_seconds: float = -1.0,
) -> dict:
    """A zoom punch (scale ``1 + punch``) on each selected beat: one ``qtblend`` per clip hit."""
    return _pulse_tool("zoom", workspace_path, track, beat_file, intensity, every_n, phase, music_track,
                       music_clip_index, music_offset_seconds, punch=punch, attack_frames=attack_frames,
                       decay_frames=decay_frames)


@mcp.tool()
@tool_guard
def beat_flash(
    workspace_path: str,
    track: int = 0,
    beat_file: str = "",
    intensity: str = "medium",
    every_n: int = 0,
    phase: int = 0,
    strength: float = 1.0,
    decay_frames: int = 3,
    music_track: int = -1,
    music_clip_index: int = 0,
    music_offset_seconds: float = -1.0,
) -> dict:
    """A brightness flash (``level`` 1 -> ``1 + strength``) on each selected beat: one filter per clip hit.

    Brightness, not opacity: an opacity dip over the black background reads as
    a dark flicker, not a flash.
    """
    return _pulse_tool("flash", workspace_path, track, beat_file, intensity, every_n, phase, music_track,
                       music_clip_index, music_offset_seconds, strength=strength, decay_frames=decay_frames)
