"""Split / quad-screen composite MCP tool (tutorial #15 bundle).

Registers ``composite_split_screen`` -- scale several source tracks into a
side-by-side, top-bottom, or quad grid computed from the project profile, then
place each into its cell by reusing the PiP/compositing machinery.

Auto-imported by ``bundles/__init__.py``. Snapshot-before-write; returns the
standard ``{"status": "success"|"error", ...}`` dicts.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err, _require_workspace


def _parse_tracks(raw: str) -> list[int]:
    """Parse a comma-separated track list like ``"1,2"`` into ``[1, 2]``."""
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not parts:
        raise ValueError("tracks must be a non-empty comma-separated list, e.g. '1,2'")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:  # non-integer token
        raise ValueError(f"tracks must be integers, got '{raw}'") from exc


@mcp.tool()
def composite_split_screen(
    workspace_path: str,
    project_file: str,
    layout: str,
    tracks: str,
    start_frame: int,
    end_frame: int,
    base_track: int = 0,
    crop: str = "fit",
    gap_px: int = 0,
    border_px: int = 0,
    border_color: str = "#000000",
) -> dict:
    """Build a split/quad-screen composite from several source tracks.

    Args:
        workspace_path: workspace root.
        project_file: ``.kdenlive`` project file within the workspace.
        layout: ``"2h"`` (side-by-side), ``"2v"`` (top-bottom), or ``"4"`` (quad).
        tracks: comma-separated cell track indices in layout order
            (2h: left,right / 2v: top,bottom / 4: TL,TR,BL,BR). 2 tracks for
            2h/2v, 4 for quad.
        start_frame, end_frame: composite duration (frames).
        base_track: background track each cell composites over (default 0).
        crop: ``"fit"`` (aspect-preserving, letterboxed) or ``"stretch"``
            (fill cell exactly, distorts aspect).
        gap_px: gutter between adjacent cells (background shows through).
        border_px: uniform inset on every cell edge (frame + gutters).
        border_color: intended background/border colour. Advisory only -- the
            composite path shows whatever is on ``base_track``; painting a solid
            colour requires a colour clip on that track (noted omission).

    Returns:
        Success dict with the computed cells and snapshot id, or an error dict.
    """
    from workshop_video_brain.edit_mcp.pipelines.split_screen import apply_split_screen
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return _err(f"Project file not found: {project_file}")

    try:
        track_list = _parse_tracks(tracks)
    except ValueError as exc:
        return _err(str(exc))

    record = create_snapshot(
        ws_path, proj_path, description=f"before_split_screen_{layout}"
    )

    project = parse_project(proj_path)
    try:
        updated, cells = apply_split_screen(
            project,
            layout=layout,
            tracks=track_list,
            start_frame=start_frame,
            end_frame=end_frame,
            base_track=base_track,
            crop=crop,
            gap_px=gap_px,
            border_px=border_px,
        )
    except (ValueError, KeyError) as exc:
        return _err(str(exc))

    serialize_project(updated, proj_path)
    return _ok({
        "layout": layout,
        "tracks": track_list,
        "base_track": base_track,
        "crop": crop,
        "gap_px": gap_px,
        "border_px": border_px,
        "border_color": border_color,
        "frames": [start_frame, end_frame],
        "cells": [
            {"x": c.x, "y": c.y, "width": c.width, "height": c.height}
            for c in cells
        ],
        "snapshot_id": record.snapshot_id,
    })
