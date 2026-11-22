"""``effect_camera_move``: zoom punch, orbit and handheld drift as a keyframed qtblend.

Shell order as ``effect_camera_shake``: parse -> validate -> snapshot -> insert
a ``qtblend`` filter -> serialize. Keyframe maths in ``pipelines/camera_moves``.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    corrupt_project,
    from_exception,
    invalid_input,
    missing_file,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _require_workspace

_SERVICE = "qtblend"


@mcp.tool()
@tool_guard
def effect_camera_move(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    move: str,
    start_frame: int = 0,
    end_frame: int = -1,
    at_frame: int = -1,
    intensity: str = "",
    radius_px: float | None = None,
    revolutions: float = 1.0,
    seed: int | None = None,
    rotation: bool = True,
) -> dict:
    """Add a named camera move to a clip as a keyframed ``qtblend`` filter.

    Moves (frames are clip-local):
    - ``zoom_punch``: a quick push that peaks at ``at_frame`` (required) and
      settles back; ``intensity`` is the extra scale, e.g. "0.15" (default).
    - ``orbit``: the frame drifts round a small circle from ``start_frame`` to
      ``end_frame`` (-1 = end of clip); ``radius_px`` (default 3 % of the
      width), ``revolutions``.
    - ``handheld``: a slow seeded wander with a little roll; ``intensity`` is
      subtle | medium (default) | aggressive; ``rotation`` false keeps it level.
    The clip is overscanned so no black edges show.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import ProjectParseError, parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import camera_moves
    from workshop_video_brain.edit_mcp.server.tools import (
        _build_filter_xml,
        _playlist_clip_duration_frames,
        _resolve_playlist,
    )
    from workshop_video_brain.workspace import create_snapshot

    if move not in camera_moves.MOVES:
        return invalid_input(f"move must be one of {', '.join(camera_moves.MOVES)}; got {move!r}",
                             "Pick zoom_punch, orbit or handheld.", param="move", given=move)
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    project_path = ws_path / project_file
    if not project_path.exists():
        return missing_file(str(project_path), "project file")
    try:
        project = parse_project(project_path)
    except ProjectParseError as exc:
        return corrupt_project(str(project_path), exc)
    fps = project.profile.fps or 25.0
    width, height = project.profile.width, project.profile.height
    try:
        playlist = _resolve_playlist(project, track)
        duration = _playlist_clip_duration_frames(playlist, clip_index)
    except (ValueError, IndexError) as exc:
        return invalid_input(str(exc), "Check track and clip_index with project_summary.")
    end = duration - 1 if end_frame < 0 else end_frame

    try:
        if move == "zoom_punch":
            if at_frame < 0:
                return invalid_input("zoom_punch needs at_frame (the clip-local frame of the hit)",
                                     "Pass at_frame, e.g. the frame of the beat or the word.", param="at_frame")
            result = camera_moves.zoom_punch(width, height, at_frame, fps,
                                             intensity=float(intensity) if intensity else 0.15)
        elif move == "orbit":
            result = camera_moves.orbit(width, height, start_frame, end, fps,
                                        radius_px=radius_px, revolutions=revolutions)
        else:
            result = camera_moves.handheld(width, height, start_frame, end, fps,
                                           intensity=intensity or "medium", seed=seed, rotation=rotation)
    except ValueError as exc:
        return invalid_input(str(exc), "Check the move's parameters against the docstring.")

    props: list[tuple[str, str]] = [("rect", result["rect"])]
    if result["rotation"] is not None:
        props += [("rotation", result["rotation"]), ("rotate_center", "1")]
    try:
        snapshot_id = create_snapshot(ws_path, project_path, description=f"before_camera_move_{move}").snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc,
                                suggestion="Make sure the workspace is writable and has free space.")
    xml = _build_filter_xml(mlt_service=_SERVICE, kdenlive_id="qtblend", track=track, clip=clip_index, props=props)
    try:
        position = len(patcher.list_effects(project, (track, clip_index)))
        patcher.insert_effect_xml(project, (track, clip_index), xml, position=position)
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), "Check track and clip_index with project_summary.")
    serialize_project(project, project_path)
    return _ok({"move": move, "effect_index": position, "service": _SERVICE,
                "keyframe_count": result["keyframe_count"], "zoom": round(result["zoom"], 4),
                "rect": result["rect"], "rotation": result["rotation"],
                "start_frame": start_frame, "end_frame": end, "at_frame": at_frame,
                "snapshot_id": snapshot_id})
