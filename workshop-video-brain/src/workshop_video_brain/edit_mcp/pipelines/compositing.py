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

import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import NamedTuple

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

MARGIN = 20
VALID_WIPE_TYPES = {"dissolve", "wipe"}

# Transform-route PiP uses the same verified ``qtblend`` clip filter as
# ``pipelines/image_overlay.py`` (render-proof: positions + composites + honours
# alpha). A bare ``rect`` on ``affine``/``transform`` is a proven no-op on this
# MLT build (affine reads ``transition.rect``; qtblend reads ``rect``), so the
# transform route deliberately uses qtblend.
PIP_TRANSFORM_SERVICE = "qtblend"
PIP_TRANSFORM_KDENLIVE_ID = "qtblend"


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


def pip_transform_rect_value(
    layout: PipLayout,
    opacity: float = 1.0,
    width_override: int | None = None,
    height_override: int | None = None,
) -> str:
    """Format a PiP layout as the qtblend ``rect`` string ``"x y w h opacity"``.

    ``width_override`` / ``height_override`` allow **non-uniform** (aspect-
    unlocked) sizing, overriding the layout's uniform width/height. ``opacity``
    is a 0-1 fraction, written as the rect's trailing opacity field.
    """
    if not 0.0 <= opacity <= 1.0:
        raise ValueError(f"opacity must be in [0.0, 1.0]; got {opacity}")
    from workshop_video_brain.edit_mcp.pipelines.image_overlay import rect_to_string

    w = int(width_override) if width_override is not None else int(layout.width)
    h = int(height_override) if height_override is not None else int(layout.height)
    if w <= 0 or h <= 0:
        raise ValueError(f"pip width/height must be > 0; got {w}x{h}")
    return rect_to_string((int(layout.x), int(layout.y), w, h), opacity)


def build_pip_transform_xml(
    overlay_track: int,
    clip_index: int,
    rect_value: str,
    rotation: float = 0.0,
) -> str:
    """Build the qtblend ``<filter>`` XML that positions/scales/rotates a PiP.

    ``rect_value`` is either a static ``"x y w h opacity"`` string or a full
    keyframe-animation string (keyframed-motion pass-through). ``rotation`` is
    in degrees (qtblend's ``rotation`` property). The association attrs
    (``track`` / ``clip_index``) are read by the serializer to relocate the
    filter inside the overlay clip's ``<entry>``, then stripped before MLT.
    """
    root = ET.Element(
        "filter",
        {
            "mlt_service": PIP_TRANSFORM_SERVICE,
            "track": str(overlay_track),
            "clip_index": str(clip_index),
        },
    )
    ET.SubElement(root, "property", {"name": "mlt_service"}).text = (
        PIP_TRANSFORM_SERVICE
    )
    ET.SubElement(root, "property", {"name": "kdenlive_id"}).text = (
        PIP_TRANSFORM_KDENLIVE_ID
    )
    ET.SubElement(root, "property", {"name": "rect"}).text = rect_value
    # compositing 0 == source-over: the overlay paints over the layers below
    # while its own alpha is preserved.
    ET.SubElement(root, "property", {"name": "compositing"}).text = "0"
    if rotation:
        ET.SubElement(root, "property", {"name": "rotation"}).text = str(rotation)
    return ET.tostring(root, encoding="unicode")


def apply_pip_transform(
    project: KdenliveProject,
    overlay_track: int,
    clip_index: int,
    rect_value: str,
    rotation: float = 0.0,
) -> KdenliveProject:
    """Insert a qtblend transform clip filter on the overlay clip (PiP route).

    This is the enhanced picture-in-picture path -- it inherits opacity,
    rotation, non-uniform sizing and keyframed motion from the verified qtblend
    clip filter (see ``pipelines/image_overlay.py``). Visibility over the base
    track comes from the serializer's per-track compositor (same as image
    overlays), so no separate composite transition is required. Returns the
    (mutated) project for call-site symmetry with :func:`apply_pip`.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher

    clip_ref = (overlay_track, clip_index)
    xml = build_pip_transform_xml(overlay_track, clip_index, rect_value, rotation)
    position = len(patcher.list_effects(project, clip_ref))
    patcher.insert_effect_xml(project, clip_ref, xml, position=position)
    return project


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
