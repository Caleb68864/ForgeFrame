"""Compositing (PiP/wipe/set) and masking/chroma tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

import json

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
    _VALID_COLOR_FORMATS_MSG,
)





# ---------------------------------------------------------------------------
# Compositing tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def composite_pip(
    workspace_path: str,
    project_file: str,
    overlay_track: int,
    base_track: int,
    start_frame: int,
    end_frame: int,
    preset: str = "bottom_right",
    scale: float = 0.25,
    opacity: float = 1.0,
    rotation: float = 0.0,
    pip_width: int | None = None,
    pip_height: int | None = None,
    rect_keyframes: str = "",
    overlay_clip_index: int = 0,
) -> dict:
    """Add a picture-in-picture composite to the project.

    Basic PiP (default) adds a cairoblend composite transition between the base
    and overlay tracks over ``[start_frame, end_frame]``.

    Supplying any of ``opacity`` (0-1), ``rotation`` (degrees), ``pip_width`` /
    ``pip_height`` (non-uniform, aspect-unlocked size), or ``rect_keyframes`` (an
    MLT rect keyframe-animation string for keyframed motion) switches to the
    **transform route**: a verified ``qtblend`` clip filter is placed on the
    overlay clip (``overlay_clip_index`` on ``overlay_track``), which the
    serializer's per-track compositor makes visible over the base. This mirrors
    the render-proven image-overlay path (a bare ``affine`` rect is a no-op on
    this MLT build, so qtblend is used).
    """
    from workshop_video_brain.core.models.compositing import PipPreset
    from workshop_video_brain.edit_mcp.pipelines.compositing import (
        apply_pip,
        apply_pip_transform,
        get_pip_layout,
        pip_transform_rect_value,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        pip_preset = PipPreset(preset)
    except ValueError:
        return _err(f"Invalid preset '{preset}'; valid values: {[p.value for p in PipPreset]}")

    use_transform = (
        opacity != 1.0
        or bool(rotation)
        or pip_width is not None
        or pip_height is not None
        or bool(rect_keyframes.strip())
    )

    create_snapshot(ws_path, proj_path, description=f"before_pip_{preset}")

    project = parse_project(proj_path)
    try:
        layout = get_pip_layout(pip_preset, project.profile.width, project.profile.height, scale)
        if use_transform:
            rect_value = (
                rect_keyframes.strip()
                if rect_keyframes.strip()
                else pip_transform_rect_value(
                    layout, opacity, pip_width, pip_height
                )
            )
            updated = apply_pip_transform(
                project, overlay_track, overlay_clip_index, rect_value, rotation
            )
        else:
            updated = apply_pip(
                project, overlay_track, base_track, start_frame, end_frame, layout
            )
    except (ValueError, KeyError, IndexError) as exc:
        return from_exception(exc)

    serialize_project(updated, proj_path)
    result = {
        "preset": preset,
        "layout": layout.model_dump(),
        "frames": [start_frame, end_frame],
        "route": "transform" if use_transform else "transition",
    }
    if use_transform:
        result.update({
            "opacity": opacity,
            "rotation": rotation,
            "overlay_clip_index": overlay_clip_index,
            "keyframed": bool(rect_keyframes.strip()),
        })
    return _ok(result)


@mcp.tool()
@tool_guard
def composite_wipe(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    wipe_type: str = "dissolve",
) -> dict:
    """Add a wipe or dissolve transition between two tracks."""
    from workshop_video_brain.edit_mcp.pipelines.compositing import apply_wipe
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    create_snapshot(ws_path, proj_path, description=f"before_wipe_{wipe_type}")

    project = parse_project(proj_path)
    try:
        updated = apply_wipe(project, track_a, track_b, start_frame, end_frame, wipe_type)
    except ValueError as exc:
        return from_exception(exc)

    serialize_project(updated, proj_path)
    return _ok({"wipe_type": wipe_type, "frames": [start_frame, end_frame]})


@mcp.tool()
@tool_guard
def composite_set(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    blend_mode: str = "cairoblend",
    geometry: str = "",
) -> dict:
    """Add a composite transition between two tracks with a named blend mode."""
    from workshop_video_brain.edit_mcp.pipelines.compositing import (
        apply_composite,
        BLEND_MODES,
    )
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    if blend_mode not in BLEND_MODES:
        return _err(
            f"Unknown blend_mode '{blend_mode}'; valid modes: {sorted(BLEND_MODES)}"
        )

    record = create_snapshot(
        ws_path, proj_path, description=f"before_composite_set_{blend_mode}"
    )

    project = parse_project(proj_path)
    try:
        geom = geometry if geometry else None
        updated = apply_composite(
            project,
            track_a=track_a,
            track_b=track_b,
            start_frame=start_frame,
            end_frame=end_frame,
            blend_mode=blend_mode,
            geometry=geom,
        )
    except ValueError as exc:
        return from_exception(exc)

    serialize_project(updated, proj_path)
    return _ok({
        "composition_added": True,
        "blend_mode": blend_mode,
        "track_a": track_a,
        "track_b": track_b,
        "snapshot_id": record.snapshot_id,
    })




# ---------------------------------------------------------------------------
# Masking (spec 2026-04-13-masking)
# ---------------------------------------------------------------------------
_VALID_MASK_TYPES = ("rotoscoping", "object_mask", "image_alpha")


_VALID_MASK_SHAPES = ("rect", "ellipse", "polygon")


def _masking_prelude(workspace_path: str, project_file: str, description: str):
    """Shared setup for masking tools.

    Returns ``(ws_path, project_path, project, snapshot_id)`` on success, or
    a ``_err`` dict on failure that the caller should return directly.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        record = create_snapshot(ws_path, project_path, description=description)
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)
    return (ws_path, project_path, project, snapshot_id)


@mcp.tool()
@tool_guard
def mask_set(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    type: str,
    params: str,
) -> dict:
    """Insert a mask filter at the top of a clip's effect stack.

    ``type`` must be one of ``rotoscoping``, ``object_mask``, ``image_alpha``.
    ``params`` is a JSON-encoded dict. A snapshot is created before writing.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    if type not in _VALID_MASK_TYPES:
        return _err(
            f"Unknown mask type {type!r}. Valid: rotoscoping, object_mask, image_alpha"
        )
    if type == "image_alpha":
        return _err(
            "image_alpha mask type not yet implemented -- use 'rotoscoping' or 'object_mask'"
        )

    try:
        param_dict = json.loads(params) if params and params.strip() else {}
    except json.JSONDecodeError as exc:
        return err(f"Invalid params JSON: {exc}", error_type="bad_json_param", suggestion='Provide a valid JSON object, e.g. {"opacity": 0.5}.', cause=str(exc))
    if not isinstance(param_dict, dict):
        return _err("params must decode to a JSON object")

    prelude = _masking_prelude(workspace_path, project_file, f"before_mask_set_{type}")
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    try:
        if type == "rotoscoping":
            try:
                mask_params = masking.MaskParams(**param_dict)
            except Exception as exc:  # pydantic ValidationError et al
                return from_exception(exc)
            xml = masking.build_rotoscoping_xml((track, clip), mask_params)
        else:  # object_mask
            xml = masking.build_object_mask_xml((track, clip), param_dict)
    except (ValueError, TypeError) as exc:
        return from_exception(exc)

    try:
        patcher.insert_effect_xml(project, (track, clip), xml, position=0)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({
        "effect_index": 0,
        "type": type,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def mask_set_shape(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    shape: str,
    bounds: str = "",
    points: str = "",
    feather: int = 0,
    feather_passes: int = 1,
    alpha_operation: str = "add",
) -> dict:
    """Insert a rotoscoping mask with a shape-derived spline at the top of a stack.

    ``shape`` is one of ``rect``, ``ellipse``, ``polygon``. ``bounds`` is a JSON
    list ``[x, y, w, h]`` (normalized). ``points`` is a JSON list of ``[x, y]``
    pairs (polygon only). A snapshot is created before writing.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    if shape not in _VALID_MASK_SHAPES:
        return _err(
            f"Unknown shape {shape!r}. Valid: rect, ellipse, polygon"
        )

    # Parse bounds / points JSON
    bounds_tuple: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    if bounds and bounds.strip():
        try:
            raw = json.loads(bounds)
        except json.JSONDecodeError as exc:
            return _err(f"Invalid bounds JSON: {exc}")
        if not isinstance(raw, list) or len(raw) != 4:
            return _err("bounds must be a JSON list of 4 numbers [x, y, w, h]")
        try:
            bounds_tuple = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        except (TypeError, ValueError) as exc:
            return _err(f"Invalid bounds values: {exc}")

    points_tuple: tuple[tuple[float, float], ...] = ()
    if points and points.strip():
        try:
            raw = json.loads(points)
        except json.JSONDecodeError as exc:
            return err(f"Invalid points JSON: {exc}", error_type="bad_json_param", suggestion='Provide a JSON list of [x, y] pairs, e.g. [[0, 0], [0.5, 0.5]].', cause=str(exc))
        if not isinstance(raw, list):
            return _err("points must be a JSON list of [x, y] pairs")
        try:
            points_tuple = tuple((float(p[0]), float(p[1])) for p in raw)
        except (TypeError, ValueError, IndexError) as exc:
            return _err(f"Invalid points values: {exc}")

    try:
        mask_shape = masking.MaskShape(
            kind=shape, bounds=bounds_tuple, points=points_tuple
        )
        sampled = masking.shape_to_points(mask_shape)
        mask_params = masking.MaskParams(
            points=sampled,
            feather=feather,
            feather_passes=feather_passes,
            alpha_operation=alpha_operation,
        )
    except Exception as exc:  # ValidationError, ValueError
        return from_exception(exc)

    prelude = _masking_prelude(
        workspace_path, project_file, f"before_mask_set_shape_{shape}"
    )
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    try:
        xml = masking.build_rotoscoping_xml((track, clip), mask_params)
        patcher.insert_effect_xml(project, (track, clip), xml, position=0)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({
        "effect_index": 0,
        "type": "rotoscoping",
        "shape": shape,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def mask_apply(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    mask_effect_index: int,
    target_effect_index: int,
) -> dict:
    """Wrap a filter with the mask_start / mask_apply sandwich.

    Converts the plain mask filter at ``mask_effect_index`` into its
    ``mask_start`` form and inserts a ``mask_apply`` after the target filter.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    prelude = _masking_prelude(workspace_path, project_file, "before_mask_apply")
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    # Early target-is-mask guard.
    try:
        filters = patcher.list_effects(project, (track, clip))
    except (IndexError, ValueError) as exc:
        return from_exception(exc)
    if 0 <= target_effect_index < len(filters):
        svc = filters[target_effect_index]["mlt_service"]
        if svc in ("mask_start", "mask_apply"):
            return _err(
                "cannot mask a mask: target effect is itself a mask filter"
            )

    try:
        result = masking.apply_mask_to_effect(
            project, (track, clip), mask_effect_index, target_effect_index
        )
    except IndexError as exc:
        try:
            available = patcher.list_effects(project, (track, clip))
        except Exception:
            available = []
        return _err(
            f"{exc}. Current stack: {len(available)} filters: {available}"
        )
    except ValueError as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({**result, "snapshot_id": snapshot_id})


@mcp.tool()
@tool_guard
def effect_chroma_key(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    color: str = "#00FF00",
    tolerance: float = 0.15,
    blend: float = 0.0,
) -> dict:
    """Append a basic ``chroma`` key filter to a clip's effect stack."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    try:
        masking.color_to_mlt_hex(color)
    except ValueError:
        return _err(_VALID_COLOR_FORMATS_MSG)

    prelude = _masking_prelude(workspace_path, project_file, "before_chroma_key")
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    try:
        xml = masking.build_chroma_key_xml((track, clip), color, tolerance, blend)
        existing = patcher.list_effects(project, (track, clip))
        position = len(existing)
        patcher.insert_effect_xml(project, (track, clip), xml, position=position)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({"effect_index": position, "snapshot_id": snapshot_id})


@mcp.tool()
@tool_guard
def effect_chroma_key_advanced(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    color: str,
    tolerance_near: float,
    tolerance_far: float,
    edge_smooth: float = 0.0,
    spill_suppression: float = 0.0,
) -> dict:
    """Append an ``avfilter.hsvkey`` advanced chroma filter to a clip."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    if tolerance_far < tolerance_near:
        return _err("tolerance_far must be >= tolerance_near")
    try:
        masking.color_to_mlt_hex(color)
    except ValueError:
        return _err(_VALID_COLOR_FORMATS_MSG)

    prelude = _masking_prelude(
        workspace_path, project_file, "before_chroma_key_advanced"
    )
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    try:
        xml = masking.build_chroma_key_advanced_xml(
            (track, clip), color, tolerance_near, tolerance_far,
            edge_smooth, spill_suppression,
        )
        existing = patcher.list_effects(project, (track, clip))
        position = len(existing)
        patcher.insert_effect_xml(project, (track, clip), xml, position=position)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({"effect_index": position, "snapshot_id": snapshot_id})


@mcp.tool()
@tool_guard
def effect_object_mask(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    enabled: bool = True,
    threshold: float = 0.5,
) -> dict:
    """Append a parametric SPOT-SHAPE alpha mask to a clip (NOT AI).

    IMPORTANT: despite the name this is **not** AI object detection. It wraps the
    stock ``frei0r.alpha0ps_alphaspot`` filter -- a geometric ellipse/rectangle
    alpha spot -- kept under this name for back-compat. For AI subject
    segmentation use ``mask_generate`` / ``mask_generate_and_apply``; to apply an
    externally-produced matte (e.g. a Kdenlive SAM2 Object Mask export) use
    ``mask_set_from_file`` (Shape Alpha).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking

    prelude = _masking_prelude(workspace_path, project_file, "before_object_mask")
    if isinstance(prelude, dict):
        return prelude
    ws_path, project_path, project, snapshot_id = prelude

    try:
        xml = masking.build_object_mask_xml(
            (track, clip), {"enabled": enabled, "threshold": threshold}
        )
        existing = patcher.list_effects(project, (track, clip))
        position = len(existing)
        patcher.insert_effect_xml(project, (track, clip), xml, position=position)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({"effect_index": position, "snapshot_id": snapshot_id})
