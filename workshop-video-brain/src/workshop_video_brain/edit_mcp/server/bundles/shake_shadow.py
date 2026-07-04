"""Camera-shake + drop-shadow bundle tools.

Derived from the Nuxttux *"Smooth Transitions, Camera Shake, Drop Shadow"*
Kdenlive tutorial (video ``V0_yp-ziqvI``), which showcases two downloadable
Kdenlive presets. This module reconstructs the achievable mechanics from
existing primitives:

* ``effect_camera_shake`` -- a deterministic, seeded pseudo-random keyframed
  ``qtblend`` (Transform) position/rotation jitter with overscan so no black
  frame edges are revealed.
* ``effect_drop_shadow`` -- the dedicated MLT ``dropshadow`` service, the clean
  single-filter path for PiP / title layers (shadow from the alpha channel).

Registers on import via ``@mcp.tool()``; auto-discovered by the ``bundles``
package. Pure math lives in ``pipelines/shake_shadow.py``.

**Known issue (§1.1, not a blocker):** clip filters currently attach at the MLT
root with ``track=`` / ``clip_index=`` attrs rather than nesting in the playlist
``<entry>`` (§1.1 of docs/plans/2026-07-03-kdenlive-mcp-improvements.md). These
tools inherit that placement behaviour until the fix lands; they still write
well-formed filter XML that relocates correctly once the serializer honours the
placement hint.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    invalid_input,
    operation_failed,
    from_exception,
    MISSING_FILE,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _require_workspace,
)


@mcp.tool()
@tool_guard
def effect_camera_shake(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    start_frame: int,
    end_frame: int,
    intensity: float = 0.5,
    frequency_hz: float = 8.0,
    seed: int | None = None,
    rotation: bool = False,
) -> dict:
    """Add a deterministic keyframed camera-shake ``qtblend`` filter to a clip.

    Reproduces the tutorial's "camera Shake medium (r for rotation)" preset as a
    seeded pseudo-random position (and optional roll) jitter. The clip is
    overscanned (zoomed) in proportion to ``intensity`` so the shifted content
    always covers the frame -- no black edges. The jitter cadence is
    ``round(fps / frequency_hz)`` frames.

    Args:
        workspace_path: Absolute path to the workspace root.
        project_file: Project file, relative to the workspace root.
        track: Video track index.
        clip_index: Clip index within the track's playlist.
        start_frame: First frame of the shake window (>= 0).
        end_frame: Last frame of the shake window; ``-1`` = end of clip.
        intensity: Shake strength in ``[0.0, 1.0]`` (0.5 ~= preset "medium").
        frequency_hz: Shakes per second (> 0).
        seed: RNG seed for reproducibility. ``None`` uses a fixed default seed,
            so output is deterministic either way.
        rotation: When true, also jitter roll (the preset's "r" variant).

    Determinism: identical inputs (including ``seed``) always produce an
    identical keyframe string.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.server.tools import (
        _build_filter_xml,
        _playlist_clip_duration_frames,
        _resolve_playlist,
    )
    from workshop_video_brain.edit_mcp.pipelines.shake_shadow import (
        SHAKE_SERVICE,
        camera_shake_keyframes,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    # Parse BEFORE snapshotting so a corrupt project fails cleanly.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
        return from_exception(exc)
    fps = project.profile.fps or 25.0
    width = project.profile.width
    height = project.profile.height

    # Resolve end_frame (-1 sentinel => end of clip).
    try:
        playlist = _resolve_playlist(project, track)
        duration = _playlist_clip_duration_frames(playlist, clip_index)
    except (ValueError, IndexError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    resolved_end = end_frame
    if resolved_end < 0:
        resolved_end = duration - 1

    try:
        shake = camera_shake_keyframes(
            width=width,
            height=height,
            start_frame=start_frame,
            end_frame=resolved_end,
            intensity=intensity,
            frequency_hz=frequency_hz,
            fps=fps,
            seed=seed,
            rotation=rotation,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    props: list[tuple[str, str]] = [("rect", shake["rect"])]
    if shake["rotation"] is not None:
        props.append(("rotation", shake["rotation"]))

    # Snapshot before write.
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_camera_shake"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    xml = _build_filter_xml(
        mlt_service=SHAKE_SERVICE,
        kdenlive_id="qtblend",
        track=track,
        clip=clip_index,
        props=props,
    )

    try:
        existing = patcher.list_effects(project, (track, clip_index))
        position = len(existing)
        patcher.insert_effect_xml(
            project, (track, clip_index), xml, position=position
        )
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)
    return _ok({
        "effect_index": position,
        "service": SHAKE_SERVICE,
        "keyframe_count": shake["keyframe_count"],
        "step_frames": shake["step_frames"],
        "zoom": round(shake["zoom"], 4),
        "intensity": float(intensity),
        "frequency_hz": float(frequency_hz),
        "rotation": bool(rotation),
        "start_frame": start_frame,
        "end_frame": resolved_end,
        "seed": seed,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_drop_shadow(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    blur_radius: int = 6,
    offset_x: int = 8,
    offset_y: int = 8,
    color: str = "#b4000000",
) -> dict:
    """Add a ``dropshadow`` filter to a clip (for PiP / title layers).

    Uses the dedicated MLT ``dropshadow`` service, which derives the shadow from
    the layer's alpha channel -- the clean single-filter path (no
    duplicate-darken-offset recipe needed). Most useful on an overlay / title
    track that already has transparency around the subject.

    Args:
        workspace_path: Absolute path to the workspace root.
        project_file: Project file, relative to the workspace root.
        track: Video track index.
        clip_index: Clip index within the track's playlist.
        blur_radius: Shadow blur radius in pixels (>= 0).
        offset_x: Shadow horizontal offset in pixels (positive = right).
        offset_y: Shadow vertical offset in pixels (positive = down).
        color: Shadow color as Kdenlive ``#AARRGGBB`` hex (alpha first).
            Default is 70%-opacity black.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.server.tools import _build_filter_xml
    from workshop_video_brain.edit_mcp.pipelines.shake_shadow import (
        DROP_SHADOW_SERVICE,
        drop_shadow_params,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    try:
        params = drop_shadow_params(
            blur_radius=blur_radius,
            offset_x=offset_x,
            offset_y=offset_y,
            color=color,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Parse BEFORE snapshotting so a corrupt project fails cleanly.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
        return from_exception(exc)

    xml = _build_filter_xml(
        mlt_service=DROP_SHADOW_SERVICE,
        kdenlive_id="dropshadow",
        track=track,
        clip=clip_index,
        props=[(k, v) for k, v in params.items()],
    )

    try:
        existing = patcher.list_effects(project, (track, clip_index))
        position = len(existing)
        patcher.insert_effect_xml(
            project, (track, clip_index), xml, position=position
        )
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Snapshot before write.
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_drop_shadow"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    serialize_project(project, project_path)
    return _ok({
        "effect_index": position,
        "service": DROP_SHADOW_SERVICE,
        "blur_radius": blur_radius,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "color": params["color"],
        "snapshot_id": snapshot_id,
    })
