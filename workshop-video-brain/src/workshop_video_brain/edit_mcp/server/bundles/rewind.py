"""``effect_rewind`` -- VHS rewind / reverse effect bundle.

Derived from Romain Pellerin's "Rewind effect (VHS style) in Kdenlive" tutorial
(https://www.youtube.com/watch?v=MnErqP9iIWU). The tutorial duplicates a clip,
speeds the copy up ~3x, reverses it, swaps in a rewinding-cassette sound, and
layers a VHS look (glitch bars, RGB split, grain, sepia).

MLT has no working reverse/timewarp producer through this file-based integration
(``clip_speed`` is a documented no-op; see
``docs/plans/2026-07-03-kdenlive-mcp-improvements.md`` s1.1 / s3-Low), so the
reliable route is ffmpeg: render the ``[start, end]`` segment of the clip's
source media reversed + sped up into ``media/processed`` (never touching
``media/raw`` originals), register it as a new producer, and insert it right
after the segment -- the classic play -> rewind -> resume pattern. Everything is
additive.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import rewind as rw
from workshop_video_brain.workspace import create_snapshot


def _resolve_producer_resource(project, producer_id: str) -> str | None:
    """Return the media resource path for a producer id, or None."""
    for prod in project.producers:
        if prod.id != producer_id:
            continue
        if prod.resource:
            return prod.resource
        return prod.properties.get("resource")
    return None


def _count_audio_streams(path: Path) -> int:
    """Number of audio streams in ``path`` via ffprobe (0 if ffprobe missing)."""
    if shutil.which("ffprobe") is None:
        return 0
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            return 0
        data = json.loads(proc.stdout or "{}")
        return len(data.get("streams", []))
    except (OSError, ValueError):
        return 0


# VHS-look effects layered onto the reversed clip when ``vhs_overlay`` is set.
# These reuse the existing effect_stack / wrapper tools; per s1.1 of the
# improvement plan the effect-stack machinery attaches filters at the MLT root
# (may not render in Kdenlive) -- a known, shared caveat, noted, not a blocker.
def _apply_vhs_overlay(
    workspace_path: str, project_file: str, track: int, clip_index: int
) -> tuple[list[str], list[dict]]:
    from workshop_video_brain.edit_mcp.server.tools import effect_glitch_stack
    from workshop_video_brain.edit_mcp.pipelines.effect_wrappers.effect_oldfilm import (
        effect_oldfilm,
    )
    from workshop_video_brain.edit_mcp.pipelines.effect_wrappers.effect_frei0r_scanline0r import (
        effect_frei0r_scanline0r,
    )

    # Under FastMCP, ``@mcp.tool()`` may return a FunctionTool wrapper whose raw
    # callable lives on ``.fn``; normalise so we can call the tool body directly.
    def _fn(tool):
        return getattr(tool, "fn", tool)

    glitch = _fn(effect_glitch_stack)
    oldfilm = _fn(effect_oldfilm)
    scanline = _fn(effect_frei0r_scanline0r)

    steps = [
        ("effect_glitch_stack",
         lambda: glitch(workspace_path, project_file, track, clip_index)),
        ("effect_oldfilm",
         lambda: oldfilm(workspace_path, project_file, track, clip_index)),
        ("effect_frei0r_scanline0r",
         lambda: scanline(workspace_path, project_file, track, clip_index)),
    ]
    applied: list[str] = []
    errors: list[dict] = []
    for name, call in steps:
        try:
            result = call()
        except Exception as exc:  # noqa: BLE001 -- overlay is best-effort
            errors.append({"effect": name, "error": str(exc)})
            continue
        if isinstance(result, dict) and result.get("status") == "success":
            applied.append(name)
        else:
            msg = result.get("message") if isinstance(result, dict) else str(result)
            errors.append({"effect": name, "error": msg})
    return applied, errors


@mcp.tool()
def effect_rewind(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    start_seconds: float,
    end_seconds: float,
    speed: float = 2.0,
    vhs_overlay: bool = True,
) -> dict:
    """Insert a VHS-style rewind (reversed, sped-up) copy of a clip segment.

    Renders the ``[start_seconds, end_seconds]`` window of the clip's *source*
    media reversed and ``speed``x faster with ffmpeg (``reverse`` / ``areverse``)
    into ``media/processed`` (originals in ``media/raw`` are never modified),
    registers it as a new producer, and inserts it immediately **after** the
    referenced clip on the same track -- the play -> rewind -> resume pattern.

    Args:
        workspace_path: Workspace root.
        project_file: Project file relative to the workspace (e.g.
            ``projects/working_copies/foo.kdenlive``).
        track: Playlist / track index the clip lives on.
        clip_index: Index of the clip within that track (real clips only, gaps
            excluded).
        start_seconds: Segment start within the source media.
        end_seconds: Segment end within the source media (> start).
        speed: Playback speed multiplier for the rewind (default 2.0). atempo
            chaining covers speeds outside ffmpeg's [0.5, 2.0] range.
        vhs_overlay: When True, layer a VHS look (glitch stack + oldfilm +
            scanlines) onto the reversed clip. Best-effort; overlay failures are
            reported in ``overlay_errors`` and never fail the tool.

    Returns a success dict with the reversed media path, new producer id, the
    inserted clip index, expected duration/frames, applied overlay effects, and
    the snapshot id -- or an error dict.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project_path = ws_path / project_file
    if not project_path.exists():
        return _err(f"Project file not found: {project_file}")

    # Validate timing / speed up front (pure).
    try:
        rw.segment_duration(start_seconds, end_seconds)
        rw.reversed_duration(start_seconds, end_seconds, speed)
    except ValueError as exc:
        return _err(str(exc))

    project = parse_project(project_path)

    # Resolve the target clip -> source media + raw playlist position.
    if track < 0 or track >= len(project.playlists):
        return _err(
            f"track {track} out of range (project has {len(project.playlists)} tracks)"
        )
    playlist = project.playlists[track]
    real_entries = [(i, e) for i, e in enumerate(playlist.entries) if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        return _err(
            f"clip_index {clip_index} out of range (track has {len(real_entries)} clips)"
        )
    raw_index, entry = real_entries[clip_index]

    resource = _resolve_producer_resource(project, entry.producer_id)
    if not resource:
        return _err(f"could not resolve source media for clip {clip_index} on track {track}")
    source = Path(resource)
    if not source.is_absolute() and not source.exists():
        source = ws_path / resource
    if not source.exists():
        return _err(f"source media not found: {source}")

    # Output goes to media/processed -- never media/raw.
    processed_dir = ws_path / "media" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    out_name = rw.reversed_clip_name(source.stem, start_seconds, end_seconds, speed)
    out_path = processed_dir / out_name
    raw_dir = (ws_path / "media" / "raw").resolve()
    if raw_dir == out_path.resolve() or raw_dir in out_path.resolve().parents:
        return _err("refusing to write reversed media into media/raw")

    # Render the reversed segment with ffmpeg.
    include_audio = _count_audio_streams(source) > 0
    args = rw.build_reverse_args(
        start_seconds, end_seconds, speed, include_audio=include_audio
    )
    result = run_ffmpeg(args, input_path=source, output_path=out_path, overwrite=True)
    if not result.success:
        return _err(f"ffmpeg reverse failed: {result.stderr[-300:]}")

    fps = project.profile.fps or 25.0
    frames = rw.reversed_frame_count(start_seconds, end_seconds, speed, fps)
    out_point = max(0, frames - 1)

    # Snapshot before mutating the project.
    try:
        snap = create_snapshot(ws_path, project_path, description="before_effect_rewind")
        snapshot_id = snap.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    # Register the reversed file as a producer and insert it after the segment.
    from workshop_video_brain.core.models.timeline import AddClip

    new_producer_id = (
        f"{out_path.stem}_{hashlib.md5(str(out_path).encode()).hexdigest()[:6]}"
    )
    intent = AddClip(
        producer_id=new_producer_id,
        track_id=playlist.id,
        track_ref=playlist.id,
        in_point=0,
        out_point=out_point,
        position=raw_index + 1,
        source_path=str(out_path),
    )
    try:
        patched = patcher.patch_project(project, [intent])
    except (ValueError, IndexError) as exc:
        return _err(f"failed to insert reversed clip: {exc}")
    serialize_project(patched, project_path)

    new_clip_index = clip_index + 1

    effects_applied: list[str] = []
    overlay_errors: list[dict] = []
    if vhs_overlay:
        effects_applied, overlay_errors = _apply_vhs_overlay(
            workspace_path, project_file, track, new_clip_index
        )

    return _ok({
        "reversed_media": str(out_path),
        "producer_id": new_producer_id,
        "inserted_position": raw_index + 1,
        "new_clip_index": new_clip_index,
        "source_media": str(source),
        "include_audio": include_audio,
        "speed": float(speed),
        "expected_duration_seconds": rw.reversed_duration(
            start_seconds, end_seconds, speed
        ),
        "expected_frames": frames,
        "vhs_overlay": vhs_overlay,
        "effects_applied": effects_applied,
        "overlay_errors": overlay_errors,
        "ffmpeg_command": result.command,
        "snapshot_id": snapshot_id,
    })
