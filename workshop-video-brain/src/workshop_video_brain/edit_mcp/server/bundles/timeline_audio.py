"""Timeline / track-level audio mixing + ducking -- §3 High "Track-level audio".

Puts mixer-style audio control *into the project timeline* (all prior ``audio_*``
tools operate on standalone files in ``media/processed/``):

* ``track_volume`` -- static or dB-keyframed ``volume`` at track scope;
* ``track_pan``   -- ``panner`` balance;
* ``track_eq``    -- stacked ``avfilter.equalizer`` bands (voice/music carve
  presets from the Nuxttux tutorials, or custom bands);
* ``audio_duck``  -- the flagship: dips a music track under speech via a keyframed
  ``volume`` envelope driven by voice-activity detection on the voice track
  (MLT has no headless live sidechain, so the duck is synthesised).

Track filters are stored as ``<filter>`` children of the track's ``<playlist>``
-- the only placement melt applies track-wide (render-verified; see
``docs/research/2026-07-03-tutorial-effect-analysis/timeline-audio-mixing.md``).

Auto-imported by ``server/bundles/__init__``; registers via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence
from workshop_video_brain.edit_mcp.pipelines import timeline_audio as ta
from workshop_video_brain.core.models.timeline import AddTrackFilter, ClearTrackFilters
from workshop_video_brain.workspace import create_snapshot


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _resolve_project(ws_path: Path, project_file: str) -> Path:
    """Resolve *project_file* to an existing .kdenlive path.

    Accepts an absolute path, a workspace-relative path, or a bare filename under
    ``projects/working_copies/``.
    """
    p = Path(project_file)
    if p.is_absolute() and p.exists():
        return p
    candidate = ws_path / project_file
    if candidate.exists():
        return candidate
    bare = ws_path / "projects" / "working_copies" / project_file
    if bare.exists():
        return bare
    raise FileNotFoundError(f"Project file not found: {project_file}")


def _track_frames(playlist) -> int:
    """Timeline length in frames of a track's playlist (entries + blanks)."""
    return sum(max(0, e.out_point - e.in_point + 1) for e in playlist.entries)


def _apply(project, project_path, ws_path, intents, description):
    """Snapshot, patch, serialise; return (snapshot_id) or raise."""
    snap = create_snapshot(ws_path, project_path, description=description)
    patched = patcher.patch_project(project, intents)
    serialize_project(patched, project_path)
    return snap.snapshot_id


def _validate_track(project, track: int) -> str | None:
    if track < 0 or track >= len(project.playlists):
        return (
            f"track {track} out of range (project has {len(project.playlists)} tracks)"
        )
    return None


# ---------------------------------------------------------------------------
# track_volume
# ---------------------------------------------------------------------------

@mcp.tool()
def track_volume(
    workspace_path: str,
    project_file: str,
    track: int,
    gain_db: float = 0.0,
    keyframes: str = "",
) -> dict:
    """Set a track's volume (a ``volume`` filter on the whole track).

    Static ``gain_db`` (dB, 0 = unity, negative = quieter) or a dB-keyframed
    envelope via ``keyframes``.  Re-running replaces the prior track-volume
    filter rather than stacking.

    Args:
        workspace_path: Workspace root.
        project_file: .kdenlive path (absolute, workspace-relative, or a bare
            filename under projects/working_copies/).
        track: Playlist / track index.
        gain_db: Static gain in dB (used when ``keyframes`` is empty).
        keyframes: Optional dB keyframes -- an MLT ``frame=db;frame=db`` string or
            a JSON array of ``{"at_seconds": t, "gain_db": g}``.

    Returns a success dict with the level string and snapshot id, or an error.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = _resolve_project(ws_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project = parse_project(project_path)
    err = _validate_track(project, track)
    if err:
        return _err(err)
    fps = project.profile.fps or 25.0

    try:
        kf = ta.parse_volume_keyframes(keyframes, fps) if keyframes else ""
    except Exception as exc:  # noqa: BLE001 - value + json errors
        return _err(f"invalid keyframes: {exc}")

    level = kf if kf else ta.fmt_db(gain_db)
    intent = AddTrackFilter(
        track_index=track,
        track_ref=project.playlists[track].id,
        mlt_service="volume",
        filter_id=f"vol{track}",
        properties={"level": level},
    )
    try:
        snapshot_id = _apply(project, project_path, ws_path, [intent], "before_track_volume")
    except Exception as exc:  # noqa: BLE001
        return _err(f"failed to apply track_volume: {exc}")

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "playlist_id": project.playlists[track].id,
        "level": level,
        "keyframed": bool(kf),
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# track_pan
# ---------------------------------------------------------------------------

@mcp.tool()
def track_pan(
    workspace_path: str,
    project_file: str,
    track: int,
    pan: float = 0.0,
) -> dict:
    """Pan a track left/right (a ``panner`` filter on the whole track).

    Args:
        workspace_path: Workspace root.
        project_file: .kdenlive path (see ``track_volume``).
        track: Playlist / track index.
        pan: -1 = full left, 0 = centre, +1 = full right.

    Returns a success dict with the panner ``start`` value and snapshot id.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = _resolve_project(ws_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project = parse_project(project_path)
    err = _validate_track(project, track)
    if err:
        return _err(err)

    try:
        start = ta.pan_to_start(pan)
    except ValueError as exc:
        return _err(str(exc))

    intent = AddTrackFilter(
        track_index=track,
        track_ref=project.playlists[track].id,
        mlt_service="panner",
        filter_id=f"pan{track}",
        properties={"start": f"{start:g}"},
    )
    try:
        snapshot_id = _apply(project, project_path, ws_path, [intent], "before_track_pan")
    except Exception as exc:  # noqa: BLE001
        return _err(f"failed to apply track_pan: {exc}")

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "playlist_id": project.playlists[track].id,
        "pan": max(-1.0, min(1.0, float(pan))),
        "panner_start": start,
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# track_eq
# ---------------------------------------------------------------------------

@mcp.tool()
def track_eq(
    workspace_path: str,
    project_file: str,
    track: int,
    preset: str = "voice_carve",
    bands: str = "",
) -> dict:
    """Apply a multi-band EQ to a track (stacked ``avfilter.equalizer`` bands).

    Presets (from the "Mix Your Voice with Music" / "Boost Your Sound Quality"
    tutorials): ``voice_carve`` (clean a voice track -- roll off rumble, lift
    presence), ``music_bed`` (carve a music track so a voice sits on top).  Pass
    ``bands`` (a JSON array of ``{"frequency", "gain_db", "width_type"?, "width"?}``)
    for a custom curve.  Re-running replaces the prior EQ band stack.

    Returns a success dict with the resolved bands and snapshot id.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = _resolve_project(ws_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project = parse_project(project_path)
    err = _validate_track(project, track)
    if err:
        return _err(err)

    try:
        resolved = ta.eq_bands(preset=preset, bands=bands or None)
    except Exception as exc:  # noqa: BLE001 - value + json errors
        return _err(f"invalid EQ spec: {exc}")

    prefix = f"eq{track}_"
    intents = [
        ClearTrackFilters(track_index=track, track_ref=project.playlists[track].id, id_prefix=prefix)
    ]
    for i, band in enumerate(resolved):
        intents.append(
            AddTrackFilter(
                track_index=track,
                track_ref=project.playlists[track].id,
                mlt_service="avfilter.equalizer",
                filter_id=f"{prefix}b{i}",
                properties=band.properties(),
                replace=False,
            )
        )
    try:
        snapshot_id = _apply(project, project_path, ws_path, intents, "before_track_eq")
    except Exception as exc:  # noqa: BLE001
        return _err(f"failed to apply track_eq: {exc}")

    return _ok({
        "kdenlive_path": str(project_path),
        "track": track,
        "playlist_id": project.playlists[track].id,
        "preset": None if bands else preset,
        "band_count": len(resolved),
        "bands": [
            {"frequency": b.frequency, "gain_db": b.gain_db, "width_type": b.width_type, "width": b.width}
            for b in resolved
        ],
        "snapshot_id": snapshot_id,
    })


# ---------------------------------------------------------------------------
# audio_duck  (flagship)
# ---------------------------------------------------------------------------

def _voice_speech_intervals(project, voice_playlist, fps, threshold_db):
    """Detect speech intervals on a voice track, in music-track timeline seconds.

    For each real clip on the voice track: resolve its source media, run
    ``detect_silence`` (the existing ffmpeg adapter), invert the silence to
    speech within the clip's source window, and offset by the clip's timeline
    start so the intervals live in the shared timeline's frame/second space.
    """
    intervals: list[tuple[float, float]] = []
    timeline_frame = 0
    producers = {p.id: p for p in project.producers}
    for entry in voice_playlist.entries:
        length = max(0, entry.out_point - entry.in_point + 1)
        if not entry.producer_id:
            timeline_frame += length
            continue
        producer = producers.get(entry.producer_id)
        resource = ""
        if producer is not None:
            resource = producer.resource or producer.properties.get("resource", "")
        src = Path(resource)
        if resource and src.exists():
            silence = detect_silence(src, threshold_db=threshold_db, min_duration=0.3)
            in_s = entry.in_point / fps
            out_s = entry.out_point / fps
            speech = ta.invert_silence(silence, in_s, out_s)
            clip_start_s = timeline_frame / fps
            for s, e in speech:
                intervals.append((clip_start_s + (s - in_s), clip_start_s + (e - in_s)))
        timeline_frame += length
    return ta.merge_intervals(intervals)


@mcp.tool()
def audio_duck(
    workspace_path: str,
    project_file: str,
    music_track: int,
    voice_track: int,
    duck_db: float = -12.0,
    attack_ms: float = 200.0,
    release_ms: float = 400.0,
    threshold_db: float = -30.0,
) -> dict:
    """Duck a music track under speech on a voice track (keyframed ``volume``).

    MLT has no headless live sidechain, so ducking is *synthesised*: voice
    activity is detected on the voice track's source audio (via the ffmpeg
    silence adapter), and a dB-keyframed ``volume`` filter on the music track
    dips to ``duck_db`` during speech with ``attack_ms`` / ``release_ms`` ramps.
    Re-running replaces the prior duck envelope.

    Args:
        workspace_path: Workspace root.
        project_file: .kdenlive path (see ``track_volume``).
        music_track: Playlist index of the music track to duck.
        voice_track: Playlist index of the voice/dialogue track.
        duck_db: Dip depth in dB (negative; e.g. -12).
        attack_ms / release_ms: Ramp durations (ms) into / out of the dip.
        threshold_db: Silence threshold (dBFS) -- quieter than this counts as
            silence, louder as speech.

    Returns a success dict with the duck count, keyframes, and snapshot id.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
        project_path = _resolve_project(ws_path, project_file)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project = parse_project(project_path)
    for label, idx in (("music_track", music_track), ("voice_track", voice_track)):
        if idx < 0 or idx >= len(project.playlists):
            return _err(
                f"{label} {idx} out of range (project has {len(project.playlists)} tracks)"
            )
    if duck_db >= 0:
        return _err("duck_db must be negative (a dip)")

    fps = project.profile.fps or 25.0
    music_playlist = project.playlists[music_track]
    voice_playlist = project.playlists[voice_track]
    total_frames = _track_frames(music_playlist)

    try:
        speech = _voice_speech_intervals(project, voice_playlist, fps, threshold_db)
    except Exception as exc:  # noqa: BLE001 - ffmpeg / fs errors
        return _err(f"voice-activity detection failed: {exc}")

    keyframes = ta.voice_activity_to_duck_keyframes(
        speech,
        total_frames=total_frames,
        fps=fps,
        duck_db=duck_db,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
    if not keyframes:
        return _ok({
            "kdenlive_path": str(project_path),
            "music_track": music_track,
            "voice_track": voice_track,
            "duck_count": 0,
            "keyframes": "",
            "note": "no speech detected on the voice track; no duck applied",
        })

    intent = AddTrackFilter(
        track_index=music_track,
        track_ref=music_playlist.id,
        mlt_service="volume",
        filter_id=f"duck{music_track}",
        properties={"level": keyframes},
    )
    try:
        snapshot_id = _apply(project, project_path, ws_path, [intent], "before_audio_duck")
    except Exception as exc:  # noqa: BLE001
        return _err(f"failed to apply audio_duck: {exc}")

    return _ok({
        "kdenlive_path": str(project_path),
        "music_track": music_track,
        "voice_track": voice_track,
        "playlist_id": music_playlist.id,
        "duck_count": len(speech),
        "speech_intervals": [[round(s, 3), round(e, 3)] for s, e in speech],
        "duck_db": duck_db,
        "attack_ms": attack_ms,
        "release_ms": release_ms,
        "keyframes": keyframes,
        "snapshot_id": snapshot_id,
    })
