"""Compositing pipeline -- PiP layouts, wipe transitions, and blend-mode composites.

Blend-mode deviation note
-------------------------
The master spec called for ``BLEND_MODE_TO_MLT: dict[str, str]`` and a single
composite service. Reality: Kdenlive's blend modes are split across TWO MLT
services -- ``frei0r.cairoblend`` (string-enum on property ``"1"``) and
``qtblend`` (integer-enum on property ``compositing``). The base MLT
``composite`` transition has no blend-mode property at all.

Accordingly, ``BLEND_MODE_TO_MLT`` is typed as ``dict[str, MltBlendTarget]``
where ``MltBlendTarget`` carries ``(service, property_name, value)``. The
abstract mode set has been authoritatively fixed at 20 modes (``subtract``
was dropped -- it has no clean native MLT mapping).
"""
from __future__ import annotations

from copy import deepcopy
from typing import NamedTuple

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

MARGIN = 20
VALID_WIPE_TYPES = {"dissolve", "wipe"}


class MltBlendTarget(NamedTuple):
    """Routing record for an abstract blend mode onto a concrete MLT service."""
    service: str
    property_name: str
    value: str


BLEND_MODES: frozenset[str] = frozenset({
    "cairoblend",
    "screen", "lighten", "darken", "multiply", "add", "overlay",
    "destination_in", "destination_out", "source_over",
    "hard_light", "soft_light", "color_dodge", "color_burn",
    "difference", "exclusion",
    "hue", "saturation", "color", "luminosity",
})


BLEND_MODE_TO_MLT: dict[str, MltBlendTarget] = {
    # frei0r.cairoblend -- string-enum on property "1"
    "cairoblend":   MltBlendTarget("frei0r.cairoblend", "1", "normal"),
    "screen":       MltBlendTarget("frei0r.cairoblend", "1", "screen"),
    "lighten":      MltBlendTarget("frei0r.cairoblend", "1", "lighten"),
    "darken":       MltBlendTarget("frei0r.cairoblend", "1", "darken"),
    "multiply":     MltBlendTarget("frei0r.cairoblend", "1", "multiply"),
    "add":          MltBlendTarget("frei0r.cairoblend", "1", "add"),
    "overlay":      MltBlendTarget("frei0r.cairoblend", "1", "overlay"),
    "hard_light":   MltBlendTarget("frei0r.cairoblend", "1", "hardlight"),
    "soft_light":   MltBlendTarget("frei0r.cairoblend", "1", "softlight"),
    "color_dodge":  MltBlendTarget("frei0r.cairoblend", "1", "colordodge"),
    "color_burn":   MltBlendTarget("frei0r.cairoblend", "1", "colorburn"),
    "difference":   MltBlendTarget("frei0r.cairoblend", "1", "difference"),
    "exclusion":    MltBlendTarget("frei0r.cairoblend", "1", "exclusion"),
    "hue":          MltBlendTarget("frei0r.cairoblend", "1", "hslhue"),
    "saturation":   MltBlendTarget("frei0r.cairoblend", "1", "hslsaturation"),
    "color":        MltBlendTarget("frei0r.cairoblend", "1", "hslcolor"),
    "luminosity":   MltBlendTarget("frei0r.cairoblend", "1", "hslluminosity"),
    # qtblend -- integer-enum on property "compositing"
    "destination_in":  MltBlendTarget("qtblend", "compositing", "6"),
    "destination_out": MltBlendTarget("qtblend", "compositing", "8"),
    "source_over":     MltBlendTarget("qtblend", "compositing", "0"),
}


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
    """Add a PiP composite composition via the shared ``apply_composite`` path."""
    geometry = f"{layout.x}/{layout.y}:{layout.width}x{layout.height}:100"
    return apply_composite(
        project,
        track_a=base_track,
        track_b=overlay_track,
        start_frame=start_frame,
        end_frame=end_frame,
        blend_mode="cairoblend",
        geometry=geometry,
    )


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


def apply_composite(
    project: KdenliveProject,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    blend_mode: str = "cairoblend",
    geometry: str | None = None,
) -> KdenliveProject:
    """Add a blend-mode composite transition between two tracks.

    ``blend_mode`` must be a member of :data:`BLEND_MODES`. Routing to the
    correct MLT service (``frei0r.cairoblend`` or ``qtblend``) is driven by
    :data:`BLEND_MODE_TO_MLT`.
    """
    if blend_mode not in BLEND_MODES:
        valid = sorted(BLEND_MODES)
        raise ValueError(
            f"Unknown blend_mode '{blend_mode}'; valid modes: {valid}"
        )
    if track_a == track_b:
        raise ValueError(
            f"track_a and track_b must be different tracks (got {track_a})"
        )
    if end_frame <= start_frame:
        raise ValueError(
            f"end_frame ({end_frame}) must be greater than start_frame ({start_frame})"
        )

    target = BLEND_MODE_TO_MLT[blend_mode]
    if geometry is None:
        geometry = f"0/0:{project.profile.width}x{project.profile.height}:100"

    params = {"geometry": geometry, target.property_name: target.value}

    intent = AddComposition(
        composition_type=target.service,
        track_a=track_a,
        track_b=track_b,
        start_frame=start_frame,
        end_frame=end_frame,
        params=params,
    )
    return patch_project(deepcopy(project), [intent])
