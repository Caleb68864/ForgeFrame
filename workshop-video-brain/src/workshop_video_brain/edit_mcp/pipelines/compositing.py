"""Compositing pipeline -- PiP layouts and wipe transitions."""
from __future__ import annotations

from copy import deepcopy

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

MARGIN = 20
VALID_WIPE_TYPES = {"dissolve", "wipe"}


def get_pip_layout(
    preset: PipPreset,
    frame_width: int,
    frame_height: int,
    pip_scale: float = 0.25,
) -> PipLayout:
    """Calculate PiP geometry from a preset and frame dimensions."""
    if preset == PipPreset.custom:
        raise ValueError("custom preset requires caller to build PipLayout directly")

    w = int(frame_width * pip_scale)
    h = int(frame_height * pip_scale)

    positions = {
        PipPreset.top_left: (MARGIN, MARGIN),
        PipPreset.top_right: (frame_width - w - MARGIN, MARGIN),
        PipPreset.bottom_left: (MARGIN, frame_height - h - MARGIN),
        PipPreset.bottom_right: (frame_width - w - MARGIN, frame_height - h - MARGIN),
        PipPreset.center: ((frame_width - w) // 2, (frame_height - h) // 2),
    }

    x, y = positions[preset]
    return PipLayout(x=x, y=y, width=w, height=h)


def apply_pip(
    project: KdenliveProject,
    overlay_track: int,
    base_track: int,
    start_frame: int,
    end_frame: int,
    layout: PipLayout,
) -> KdenliveProject:
    """Add a PiP composite composition to the project."""
    geometry = f"{layout.x}/{layout.y}:{layout.width}x{layout.height}:100"
    intent = AddComposition(
        composition_type="composite",
        track_a=base_track,
        track_b=overlay_track,
        start_frame=start_frame,
        end_frame=end_frame,
        params={"geometry": geometry},
    )
    return patch_project(deepcopy(project), [intent])


def apply_wipe(
    project: KdenliveProject,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    wipe_type: str = "dissolve",
) -> KdenliveProject:
    """Add a wipe/dissolve transition between two tracks."""
    if wipe_type not in VALID_WIPE_TYPES:
        raise ValueError(f"Invalid wipe_type '{wipe_type}'; must be one of {VALID_WIPE_TYPES}")

    params: dict[str, str] = {}
    if wipe_type == "dissolve":
        params["resource"] = ""
    else:  # wipe
        params["resource"] = "/usr/share/kdenlive/lumas/HD/luma01.pgm"

    intent = AddComposition(
        composition_type="luma",
        track_a=track_a,
        track_b=track_b,
        start_frame=start_frame,
        end_frame=end_frame,
        params=params,
    )
    return patch_project(deepcopy(project), [intent])
