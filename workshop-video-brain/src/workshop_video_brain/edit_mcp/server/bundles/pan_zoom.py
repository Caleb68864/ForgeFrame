"""``effect_pan_zoom`` -- Ken Burns pan/zoom bundle tool.

Derived from the "How to Use Keyframes" tutorial (see
``docs/research/2026-07-03-tutorial-effect-analysis/keyframes-panzoom.md``).
Registers one MCP tool that adds a keyframed ``affine``/``transform`` filter
to a clip, animating a source-region rect from ``start_rect`` to ``end_rect``
(or from a profile-computed ``preset``). Geometry lives in the pure module
``pipelines/pan_zoom.py``; the keyframe string is emitted through the existing
``pipelines/keyframes.py`` machinery, same as ``effect_keyframe_set_rect``.

Auto-imported by ``server/bundles/__init__.py``. Snapshot-before-write; all
failures returned as ``{"status": "error", ...}`` dicts.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
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
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err

_MLT_SERVICE = "affine"
_KDENLIVE_ID = "transform"
# ``affine`` reads ``transition.rect`` -- a bare ``rect`` here is a proven no-op
# on this MLT build (render-verified). See pan_zoom.build_pan_zoom_transform_keyframes.
_RECT_PROPERTY = "transition.rect"


def _find_workspace_root(project_path: Path) -> Path:
    """Locate the workspace root (nearest ancestor holding ``workspace.yaml``).

    Falls back to the project file's own directory when no workspace manifest
    is found -- snapshots then land in ``<dir>/projects/snapshots``.
    """
    for parent in (project_path.parent, *project_path.parents):
        if (parent / "workspace.yaml").exists():
            return parent
    return project_path.parent


def _build_transform_xml(track: int, clip_index: int, rect_kf: str) -> str:
    root = ET.Element(
        "filter",
        {
            "mlt_service": _MLT_SERVICE,
            "track": str(track),
            "clip_index": str(clip_index),
        },
    )
    svc = ET.SubElement(root, "property", {"name": "mlt_service"})
    svc.text = _MLT_SERVICE
    kid = ET.SubElement(root, "property", {"name": "kdenlive_id"})
    kid.text = _KDENLIVE_ID
    rect = ET.SubElement(root, "property", {"name": _RECT_PROPERTY})
    rect.text = rect_kf
    return ET.tostring(root, encoding="unicode")


@mcp.tool()
@tool_guard
def effect_pan_zoom(
    project_file: str,
    track: int,
    clip_index: int,
    start_rect: list[float] | None = None,
    end_rect: list[float] | None = None,
    preset: str | None = None,
    duration_frames: int | None = None,
    easing: str = "cubic_in_out",
    hold_frames: int = 0,
) -> dict:
    """Add a keyframed pan/zoom (Ken Burns) transform to a clip.

    Animates a source-region rect ``(x y w h)`` -- the region scaled up to
    fill the frame -- from ``start_rect`` to ``end_rect`` over the clip (or
    ``duration_frames``). Provide explicit rects, a ``preset``, or both (rects
    override the matching side of the preset). Rects are clamped to frame
    bounds. Emits a keyframed ``affine``/``transform`` filter via the shared
    keyframe pipeline. Snapshots the project before writing.

    Args:
        project_file: Absolute path to the ``.kdenlive`` project file.
        track: Playlist/track index of the clip.
        clip_index: 0-based clip index within the track.
        start_rect: ``[x, y, w, h]`` source region at the start (optional).
        end_rect: ``[x, y, w, h]`` source region at the end (optional).
        preset: One of ``pan_zoom.PRESETS`` (e.g. ``"zoom_in"``,
            ``"pan_left_to_right"``, ``"kenburns_tl_br"``); computed from the
            project profile.
        duration_frames: Move length in frames. Defaults to the clip length.
        easing: Interpolation name for the move (default ``"cubic_in_out"``).
        hold_frames: Frames to hold the start rect before the move (lead-in).

    Returns:
        Success dict with the written keyframe string, resolved rects and the
        snapshot id, or an error dict.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.pipelines.pan_zoom import (
        build_pan_zoom_transform_keyframes,
        clamp_rect,
        preset_rects,
    )
    from workshop_video_brain.workspace import create_snapshot

    if not project_file or not project_file.strip():
        return invalid_input("project_file must be a non-empty string", suggestion="Pass a non-empty value for this argument.")
    project_path = Path(project_file)
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    if start_rect is None and end_rect is None and preset is None:
        return _err(
            "provide either a preset or both start_rect and end_rect"
        )

    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
        ProjectParseError,
    )
    try:
        project = parse_project(project_path)
    except ProjectParseError as exc:
        return corrupt_project(str(project_path), exc)
    fps = project.profile.fps or 25.0
    width = project.profile.width
    height = project.profile.height

    # Validate track / clip and resolve the clip length for the default
    # duration.
    if track < 0 or track >= len(project.playlists):
        return invalid_index(
            "track", track, f"0..{len(project.playlists) - 1}"
        )
    real_entries = [e for e in project.playlists[track].entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        upper = len(real_entries) - 1
        return invalid_index(
            "clip_index", clip_index,
            f"0..{upper}" if real_entries else "no clips on this track",
        )
    entry = real_entries[clip_index]

    if duration_frames is None:
        clip_len = entry.out_point - entry.in_point + 1
        duration_frames = clip_len if clip_len > 0 else int(round(fps * 5))

    # Resolve rects: preset (profile-computed) then explicit overrides.
    try:
        if preset is not None:
            p_start, p_end = preset_rects(preset, width, height)
        else:
            p_start = p_end = None
        chosen_start = start_rect if start_rect is not None else p_start
        chosen_end = end_rect if end_rect is not None else p_end
        if chosen_start is None or chosen_end is None:
            return _err(
                "provide either a preset or both start_rect and end_rect"
            )
        final_start = clamp_rect(chosen_start, width, height)
        final_end = clamp_rect(chosen_end, width, height)
        # ``final_*`` are the intuitive source regions reported to the caller;
        # the emitted keyframes are the affine *destination* rects (transform
        # that actually moves pixels -- a bare ``rect`` on affine is a no-op).
        rect_kf = build_pan_zoom_transform_keyframes(
            final_start, final_end, width, height, duration_frames, fps,
            easing=easing, hold_frames=hold_frames,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    clip_ref = (track, clip_index)
    try:
        effect_index = len(patcher.list_effects(project, clip_ref))
    except IndexError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Snapshot before write.
    ws_root = _find_workspace_root(project_path)
    try:
        record = create_snapshot(
            ws_root, project_path, description="before_pan_zoom"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001 - surface snapshot failure as error
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    xml = _build_transform_xml(track, clip_index, rect_kf)
    try:
        patcher.insert_effect_xml(project, clip_ref, xml, position=effect_index)
    except IndexError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)

    return _ok({
        "project_file": str(project_path),
        "track": track,
        "clip_index": clip_index,
        "effect_index": effect_index,
        "mlt_service": _MLT_SERVICE,
        "kdenlive_id": _KDENLIVE_ID,
        "property": _RECT_PROPERTY,
        "preset": preset,
        "start_rect": list(final_start),
        "end_rect": list(final_end),
        "duration_frames": duration_frames,
        "hold_frames": hold_frames,
        "easing": easing,
        "width": width,
        "height": height,
        "fps": fps,
        "keyframes_written": rect_kf,
        "snapshot_id": snapshot_id,
    })
