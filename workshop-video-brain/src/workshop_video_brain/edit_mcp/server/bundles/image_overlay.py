"""Single-image / PNG overlay bundle tools: ``overlay_insert`` + ``watermark_apply``.

Closes gap-analysis item 4 (SYNTHESIS #9 remainder): a single still -- an
instruction diagram, a logo/watermark, a step-number card -- placed on a video
track *above* the footage so it composites over it.

Model-level, titles-style (``server/bundles/titles.py``): register a ``qimage``
image producer on the project model and drop a blank-padded ``PlaylistEntry`` on
a top / specified video track.  The serializer's per-track always-active
``frei0r.cairoblend`` compositor makes the upper track visible over the footage
and honours the still's alpha -- so no explicit ``composite_set`` is needed.
Optional geometry (corner watermark, scaled diagram) and opacity fades ride a
single ``qtblend`` clip filter.  Pure logic lives in
``pipelines/image_overlay.py``; this module does snapshot + XML I/O and returns
the ``_ok`` / ``_err`` envelopes.

Registered by the ``bundles`` package auto-importer.  Touches no
``adapters/kdenlive/`` code, no ``server/tools.py``, no ``server.py``.
"""
from __future__ import annotations

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
    from_exception,
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


def _place_image_overlay(
    project,
    image_path: str,
    at_frame: int,
    duration_frames: int,
    track: int | None,
    rect_arg: str,
    opacity: float,
    scale: float,
    fade_in_frames: int,
    fade_out_frames: int,
) -> dict:
    """Register the image producer, place a blank-padded entry, add the qtblend
    transform.  Mutates *project* in place; returns a result-data dict.

    Raises ``ValueError`` on bad geometry / track / fade arguments.
    """
    from workshop_video_brain.core.models.kdenlive import (
        Playlist,
        Producer,
        Track,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
    from workshop_video_brain.edit_mcp.pipelines import image_overlay as io

    fps = project.profile.fps or 25.0
    width, height = project.profile.width, project.profile.height

    # --- resolve geometry up front (fail before mutating) --------------
    aspect = io.image_aspect(image_path)
    rect = io.resolve_rect(
        rect_arg, width, height, scale=scale, margin=0.05, aspect=aspect
    )
    if fade_in_frames < 0 or fade_out_frames < 0:
        raise ValueError("fade frames must be >= 0")
    if fade_in_frames + fade_out_frames > duration_frames:
        raise ValueError(
            f"fade_in_frames + fade_out_frames ({fade_in_frames + fade_out_frames}) "
            f"exceeds duration ({duration_frames} frames)"
        )

    # --- register the image producer -----------------------------------
    producer_id = io.image_producer_id(image_path)
    if producer_id not in {p.id for p in project.producers}:
        project.producers.append(
            Producer(
                id=producer_id,
                resource=str(image_path),
                properties=io.image_producer_properties(image_path, duration_frames),
            )
        )

    # --- resolve / create the target top video track -------------------
    vps = io.video_playlists(project)
    if track is None:
        base = "playlist_image"
        all_ids = {t.id for t in project.tracks} | {p.id for p in project.playlists}
        track_id = base
        n = 1
        while track_id in all_ids:
            track_id = f"{base}_{n}"
            n += 1
        project.tracks.append(Track(id=track_id, track_type="video", name="Overlay"))
        target = Playlist(id=track_id)
        project.playlists.append(target)
        resolved_track = len(vps)  # index of the new top video track
        new_track = True
    else:
        if track < 0 or track >= len(vps):
            raise ValueError(
                f"track index {track} out of range "
                f"(project has {len(vps)} video track(s))"
            )
        target = vps[track]
        resolved_track = track
        new_track = False

    # --- place the still at at_frame via the canonical clip_place engine
    # (absolute overwrite placement, pinned to never overlap existing content --
    # the engine emits the leading pad blank).
    at_frame = max(0, at_frame)
    placed = cp.PlacedClip(
        producer_id=producer_id, in_point=0, out_point=duration_frames - 1
    )
    place_at = max(at_frame, cp.playlist_length(target.entries))
    result = cp.plan_overwrite(target.entries, place_at, placed)
    target.entries = result.entries
    clip_index = result.placed_index

    # --- transform filter (position / scale / opacity / fades) ---------
    # Needed whenever geometry, non-unit opacity, or a fade is requested.
    need_filter = rect is not None or opacity != 1.0 or fade_in_frames or fade_out_frames
    transform_added = False
    if need_filter:
        geom = rect if rect is not None else (0, 0, width, height)
        rect_value = io.overlay_rect_value(
            geom,
            opacity=opacity,
            fade_in_frames=fade_in_frames,
            fade_out_frames=fade_out_frames,
            duration_frames=duration_frames,
            fps=fps,
        )
        playlist_index = project.playlists.index(target)
        xml = io.build_transform_filter_xml(playlist_index, clip_index, rect_value)
        existing = patcher.list_effects(project, (playlist_index, clip_index))
        patcher.insert_effect_xml(
            project, (playlist_index, clip_index), xml, position=len(existing)
        )
        transform_added = True

    return {
        "producer_id": producer_id,
        "producer_service": io.IMAGE_PRODUCER_SERVICE,
        "track": resolved_track,
        "track_id": target.id,
        "new_track": new_track,
        "at_frame": at_frame,
        "duration_frames": duration_frames,
        "rect": list(rect) if rect is not None else None,
        "opacity": float(opacity),
        "fade_in_frames": fade_in_frames,
        "fade_out_frames": fade_out_frames,
        "transform_added": transform_added,
        "is_svg": io.is_svg(image_path),
    }


@mcp.tool()
@tool_guard
def overlay_insert(
    workspace_path: str,
    project_file: str,
    image_path: str,
    at_seconds: float,
    duration_seconds: float = 5.0,
    track: int | None = None,
    rect: str = "",
    opacity: float = 1.0,
    fade_in_frames: int = 0,
    fade_out_frames: int = 0,
    scale: float = 0.15,
) -> dict:
    """Place a single still (PNG/JPG/SVG) on a track above the footage.

    Registers a ``qimage`` image producer and drops it on a top (or specified)
    video track at ``at_seconds`` for ``duration_seconds``, titles-style.  The
    serializer's always-active per-track compositor makes it visible over the
    footage and honours the image's alpha, so a transparent PNG / SVG shows the
    footage through its transparent regions with no extra step.

    Use it for instruction diagrams, logo/watermark stills, or step-number
    cards.  A snapshot is taken before the project is written.

    Args:
        workspace_path: Workspace root.
        project_file: ``.kdenlive`` file, relative to the workspace.
        image_path: Path to the still (``.png`` / ``.jpg`` / ``.svg`` / ...).
        at_seconds: Timeline position of the still, in seconds.
        duration_seconds: How long the still holds on screen.
        track: Video-track index to place on.  ``None`` (default) creates a new
            dedicated top video track.
        rect: Optional geometry.  Empty = fill the frame.  A placement preset
            (``top_left`` / ``top_right`` / ``bottom_left`` / ``bottom_right`` /
            ``center`` / ``full``) computes a corner box from the profile using
            ``scale``.  Or an explicit ``"x y w h"`` pixel rectangle.
        opacity: ``[0.0, 1.0]`` overlay opacity.
        fade_in_frames / fade_out_frames: optional opacity fades on the still.
        scale: box size (fraction of frame width) for corner/preset placement.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import image_overlay as io
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
    if not image_path or not str(image_path).strip():
        return err("image_path must be a non-empty path", suggestion="Pass the path to the image you want to overlay (PNG/JPG); it resolves under the workspace root unless absolute.")
    if not Path(image_path).exists():
        return err(f"image_path does not exist: {image_path}", suggestion="Check the image path; it resolves under the workspace root unless absolute.")
    if not io.is_supported_image(image_path):
        return err(
            f"unsupported image type {Path(image_path).suffix!r}; "
            f"supported: {sorted(io.IMAGE_EXTENSIONS)}",
            suggestion="Convert the image to a supported format (PNG or JPG) and pass that instead.",
        )
    if at_seconds < 0:
        return err("at_seconds must be >= 0", suggestion="Pass at_seconds as 0 or more (the second on the timeline where the overlay starts).")
    if duration_seconds <= 0:
        return err("duration_seconds must be > 0", suggestion="Pass a positive duration_seconds for how long the overlay stays on screen.")
    if not 0.0 <= float(opacity) <= 1.0:
        return err(f"opacity must be in [0.0, 1.0]; got {opacity}", suggestion="Pass opacity as a fraction between 0.0 (invisible) and 1.0 (solid).")

    # Parse BEFORE snapshotting so a corrupt project fails cleanly
    # (corrupt_project) without leaving a leaked snapshot behind.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
        return from_exception(exc)
    fps = project.profile.fps or 25.0
    at_frame = max(0, round(at_seconds * fps))
    duration_frames = max(1, round(duration_seconds * fps))

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_overlay_insert"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    try:
        data = _place_image_overlay(
            project,
            image_path=str(image_path),
            at_frame=at_frame,
            duration_frames=duration_frames,
            track=track,
            rect_arg=rect,
            opacity=float(opacity),
            scale=float(scale),
            fade_in_frames=int(fade_in_frames),
            fade_out_frames=int(fade_out_frames),
        )
    except (ValueError, IndexError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)
    data.update(
        {
            "project_file": str(project_path),
            "image_path": str(image_path),
            "at_seconds": at_seconds,
            "duration_seconds": duration_seconds,
            "snapshot_id": snapshot_id,
        }
    )
    return _ok(data)


@mcp.tool()
@tool_guard
def watermark_apply(
    workspace_path: str,
    project_file: str,
    image_path: str,
    position: str = "bottom_right",
    scale: float = 0.15,
    opacity: float = 0.6,
) -> dict:
    """Apply a full-duration corner watermark from an image.

    Convenience over :func:`overlay_insert`: computes a corner rectangle from the
    project profile (keeping the logo's aspect ratio when Pillow is available),
    then places the still from frame 0 across the whole timeline at a reduced
    ``opacity``.  A snapshot is taken before the project is written.

    Args:
        workspace_path: Workspace root.
        project_file: ``.kdenlive`` file, relative to the workspace.
        image_path: Path to the watermark / logo still.
        position: Corner preset -- ``bottom_right`` (default), ``bottom_left``,
            ``top_right``, ``top_left``, or ``center``.
        scale: Watermark box size as a fraction of the frame width.
        opacity: ``[0.0, 1.0]`` watermark opacity (default 0.6).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import image_overlay as io
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
    if not image_path or not str(image_path).strip():
        return err("image_path must be a non-empty path", suggestion="Pass the path to the image you want to overlay (PNG/JPG); it resolves under the workspace root unless absolute.")
    if not Path(image_path).exists():
        return err(f"image_path does not exist: {image_path}", suggestion="Check the image path; it resolves under the workspace root unless absolute.")
    if not io.is_supported_image(image_path):
        return err(
            f"unsupported image type {Path(image_path).suffix!r}; "
            f"supported: {sorted(io.IMAGE_EXTENSIONS)}",
            suggestion="Convert the image to a supported format (PNG or JPG) and pass that instead.",
        )
    if position == "full" or position not in io.POSITION_PRESETS:
        return err(
            f"position must be a corner/center preset; got {position!r} "
            f"(valid: top_left, top_right, bottom_left, bottom_right, center)",
            suggestion="Pass position as one of: top_left, top_right, bottom_left, bottom_right, center.",
        )
    if not 0.0 <= float(opacity) <= 1.0:
        return err(f"opacity must be in [0.0, 1.0]; got {opacity}", suggestion="Pass opacity as a fraction between 0.0 (invisible) and 1.0 (solid).")

    # Parse BEFORE snapshotting so a corrupt project fails cleanly
    # (corrupt_project) without leaving a leaked snapshot behind.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
        return from_exception(exc)
    duration_frames = io.timeline_duration_frames(project)
    if duration_frames <= 0:
        return err("The project timeline is empty, so there is nothing to watermark.", suggestion="Add clips to the timeline first, then apply the watermark.")

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_watermark_apply"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    try:
        data = _place_image_overlay(
            project,
            image_path=str(image_path),
            at_frame=0,
            duration_frames=duration_frames,
            track=None,
            rect_arg=position,
            opacity=float(opacity),
            scale=float(scale),
            fade_in_frames=0,
            fade_out_frames=0,
        )
    except (ValueError, IndexError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)
    data.update(
        {
            "project_file": str(project_path),
            "image_path": str(image_path),
            "position": position,
            "scale": float(scale),
            "duration_frames": duration_frames,
            "snapshot_id": snapshot_id,
        }
    )
    return _ok(data)
