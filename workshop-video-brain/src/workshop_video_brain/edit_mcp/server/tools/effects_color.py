"""Color analysis/LUT, color-wash/grade, and paper-cutout/greenscreen bundles.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

import json
from pathlib import Path

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
    operation_failed,
    from_exception,
    nonfinite_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
    _build_filter_xml,
    _VALID_COLOR_FORMATS_MSG,
    _lookup_catalog_by_service,
)



@mcp.tool()
@tool_guard
def color_analyze(file_path: str) -> dict:
    """Analyze color metadata of a media file.

    Returns color space, primaries, transfer characteristics, HDR detection,
    and actionable recommendations for delivery workflows.
    """
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    if not file_path or not file_path.strip():
        return invalid_input("file_path must be a non-empty string", "Pass the path to a media file to analyze.", param="file_path")
    p = Path(file_path)
    if not p.exists():
        return err(f"File not found: {file_path}", error_type="missing_file", suggestion="Check the file path is correct and the file exists.", path=str(file_path))
    if p.is_dir():
        return invalid_input(f"file_path is a directory, not a file: {file_path}", "Pass the path to a single media file, not a folder.", path=str(file_path))

    analysis = analyze_color(p)
    return _ok(analysis.model_dump())


@mcp.tool()
@tool_guard
def color_apply_lut(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    lut_path: str,
    interp: str = "",
) -> dict:
    """Apply a LUT file to a clip in a Kdenlive project.

    Creates a snapshot before modifying the project. The LUT is applied via
    the avfilter.lut3d effect and appended to any existing effects on the clip.

    Args:
        interp: Optional lut3d interpolation mode -- ``nearest`` / ``trilinear``
            / ``tetrahedral`` / ``pyramid`` / ``prism`` (sets ``av.interp``).
            Empty leaves it unset (ffmpeg default = ``tetrahedral``, smoothest).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    lut = Path(lut_path)
    if not lut.exists():
        return _err(f"LUT file not found: {lut_path}")

    # Snapshot before modify
    create_snapshot(ws_path, project_path, description=f"before_lut_{lut.stem}")

    project = parse_project(project_path)
    try:
        patched = apply_lut_to_project(
            project, track, clip, str(lut), interp=interp or None
        )
    except (IndexError, ValueError) as exc:
        return _err(f"Failed to apply LUT: {exc}")

    serialize_project(patched, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "lut_applied": str(lut),
        "interp": (interp or "").strip().lower() or None,
    })


@mcp.tool()
@tool_guard
def effect_color_wash(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    color: str = "blue",
    intensity: float = 0.5,
    opacity: float = 0.6,
) -> dict:
    """Append a light-wash ("Color Wash VFX") colour-grade stack to a clip.

    Reproduces the whole-clip colour grade from Photolearningism's "Master Color
    Wash VFX in Kdenlive" tutorial (simulating coloured light -- e.g. a
    lightsaber -- spilling onto a subject). Four filters are appended in one
    snapshot, in this order:

    1. ``frei0r.colorize`` -- the wash tint (hue from ``color``; saturation
       scaled by ``intensity``).
    2. ``frei0r.transparency`` -- tones the wash down (``opacity``).
    3. ``frei0r.brightness`` -- a subtle glow lift (scaled by ``intensity``).
    4. ``frei0r.contrast0r`` -- a matching contrast boost.

    Args:
        color: Wash colour name (red, orange, yellow, green, cyan, blue, purple,
            magenta) or a normalized hue float in ``[0.0, 1.0]``.
        intensity: ``[0.0, 1.0]`` -- scales saturation, brightness and contrast.
        opacity: ``[0.0, 1.0]`` -- the transparency amount (1.0 = fully applied).

    Honest-subset omissions (see the analysis report for detail):

    * The tutorial confines the wash to the subject / room with an *animated*
      rotoscoping mask. Per-frame roto is a known hard blocker
      (``masking._spline_json`` emits frame 0 only), so the wash is applied to
      the whole clip. Add static region-scoping separately with
      ``mask_set`` / ``mask_apply``.
    * The tutorial duplicates the clip onto opaque under-layers for the
      transparency to bleed onto; cross-track clip duplication is not an
      available primitive, so a single clip is graded.
    * Parameters are static. Keyframe lightness / brightness afterwards with
      ``effect_keyframe_set_scalar`` to pulse the wash over time.
    * Filter placement (§1.1/§1.2 of docs/plans/2026-07-03-kdenlive-mcp-
      improvements.md) is a known open issue shared by every effect tool here.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.color_wash import (
        COLOR_WASH_SERVICES,
        color_wash_params,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    nf = nonfinite_guard(intensity=intensity, opacity=opacity)
    if nf is not None:
        return nf

    try:
        stack = color_wash_params(color=color, intensity=intensity, opacity=opacity)
    except ValueError as exc:
        return from_exception(exc)

    # Verify every service is in the catalog up front.
    resolved: list[tuple[str, str, dict[str, str]]] = []
    for svc in COLOR_WASH_SERVICES:
        kid, _eff = _lookup_catalog_by_service(svc)
        if kid is None:
            return _err(f"missing catalog service: {svc}")
        params = dict(next(p for s, p in stack if s == svc))
        resolved.append((svc, kid, params))

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_color_wash"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)

    try:
        existing = patcher.list_effects(project, (track, clip))
    except (IndexError, ValueError) as exc:
        return from_exception(exc)
    first_effect_index = len(existing)

    inserted = 0
    for svc, kid, params in resolved:
        xml = _build_filter_xml(
            mlt_service=svc,
            kdenlive_id=kid,
            track=track,
            clip=clip,
            props=[(k, v) for k, v in params.items()],
        )
        try:
            patcher.insert_effect_xml(
                project, (track, clip), xml, position=first_effect_index + inserted
            )
        except (IndexError, ValueError) as exc:
            return operation_failed(f"partial failure after {inserted} filters", cause=exc, suggestion="A filter could not be inserted mid-chain. Restore a snapshot and retry with a valid track/clip.")
        inserted += 1

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "color": color,
        "intensity": float(intensity),
        "opacity": float(opacity),
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_color_grade(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    temperature: float = 6500.0,
    exposure: float = 0.0,
    black_level: float = 0.0,
    contrast: float = 1.0,
    brightness: float = 0.0,
    saturation: float = 1.0,
    lift: float = 0.0,
    gamma: float = 0.0,
    gain: float = 0.0,
    tint_amount: float = 0.0,
    tint_shadows: str = "0x000000ff",
    tint_highlights: str = "0x00ff00ff",
    lut_path: str = "",
) -> dict:
    """Apply a correction+grade chain to a clip in one snapshot.

    Bundles the Nuxttux "Color Correction & Grading" tutorial workflow into a
    single call. Emits, in top-to-bottom order, only the stages whose params
    depart from neutral:

    Correction -- ``avfilter.colortemperature`` (white balance), then
    ``avfilter.exposure`` (exposure / dark point), then ``avfilter.eq``
    (contrast / brightness / saturation).

    Grade -- ``lumaliftgaingamma`` (lift / gamma / gain wheels), optional
    ``frei0r.tint0r`` (creative tint, off when ``tint_amount`` == 0), optional
    ``avfilter.lut3d`` (creative LUT, off when ``lut_path`` == "").

    Neutral defaults (temperature 6500, exposure/black/lift/gamma/gain 0,
    contrast/saturation 1, brightness 0, tint_amount 0, empty lut_path) mean a
    stage left untouched is not inserted. At least one param must be non-neutral.
    All filters are inserted under a single before-image snapshot.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.pipelines.color_grade import (
        build_color_grade_chain,
    )
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    nf = nonfinite_guard(
        temperature=temperature, exposure=exposure, black_level=black_level,
        contrast=contrast, brightness=brightness, saturation=saturation,
        lift=lift, gamma=gamma, gain=gain, tint_amount=tint_amount,
    )
    if nf is not None:
        return nf

    if lut_path:
        lut_p = Path(lut_path)
        if not lut_p.is_absolute() or not lut_p.exists():
            return missing_file(lut_path, "lut_path (absolute path required)")

    try:
        chain = build_color_grade_chain(
            temperature=temperature,
            exposure=exposure,
            black_level=black_level,
            contrast=contrast,
            brightness=brightness,
            saturation=saturation,
            lift=lift,
            gamma=gamma,
            gain=gain,
            tint_amount=tint_amount,
            tint_shadows=tint_shadows,
            tint_highlights=tint_highlights,
            lut_path=lut_path,
        )
    except ValueError as exc:
        return from_exception(exc)

    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(project_path)
    try:
        existing = patcher.list_effects(project, (track, clip))
    except (IndexError, ValueError) as exc:
        return from_exception(exc)
    first_effect_index = len(existing)

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_color_grade"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    applied: list[str] = []
    for service, params in chain:
        try:
            project = apply_effect(project, track, clip, service, params)
        except (IndexError, ValueError) as exc:
            return _err(f"partial failure after {len(applied)} filters: {exc}")
        applied.append(service)

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": len(applied),
        "services": applied,
        "snapshot_id": snapshot_id,
    })




# ---------------------------------------------------------------------------
# Paper-cutout transition bundle (tutorial: Mint Visual "Paper Cutout Transition")
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def transition_paper_cutout(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    points: str = "",
    feather: int = 2,
    feather_passes: int = 2,
    alpha_operation: str = "add",
    edge_scale: float = 1.0,
    distort_amplitude: float = 0.0,
    distort_frequency: float = 0.02,
    drop_shadow: bool = True,
    shadow_offset: int = 4,
    shadow_blur: float = 8.0,
    shadow_color: str = "#000000",
) -> dict:
    """Stamp a torn-paper cutout filter stack onto a clip in one snapshot.

    Distilled from Mint Visual's *"Kdenlive | Paper Cutout Transition"*
    tutorial (``Fh1xhOzfjBE``). Applies, in application order:

    1. **Transform** (``affine``) -- centred uniform ``edge_scale`` (only when
       ``!= 1.0``; the white-rim / paper-edge trick).
    2. **Rotoscoping** mask (``rotoscoping``) -- the torn subject outline.
       ``points`` is a JSON list of ``[x, y]`` normalized pairs (>= 3); when
       empty a deterministic procedural torn polygon is used. ``feather`` and
       ``feather_passes`` default to 2 (per the tutorial).
    3. **Distort** (``frei0r.distort0r``) -- edge-roughening (only when
       ``distort_amplitude > 0``).
    4. **Drop shadow** (``dropshadow``) -- black paper-lift shadow (when
       ``drop_shadow`` is true).

    This reproduces the *per-clip* torn-cutout look. The tutorial's full
    transition also spans a stepped multi-still reveal, a screen-blended paper
    texture layer, and a separate white-edge track -- those require producers
    the MCP surface does not yet expose (extract-frame-to-project, single-image
    and solid-colour producers) and hand-drawn per-still roto splines, and are
    NOT performed here. For the paper-texture overlay use
    ``composite_set(blend_mode="screen")`` on its own track (subject to the
    §1.2 transition-placement bug). See the analysis report for the full map.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import paper_cutout
    from workshop_video_brain.workspace import create_snapshot

    # Parse optional polygon points.
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
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_transition_paper_cutout"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)
    width = project.profile.width
    height = project.profile.height

    try:
        xmls = paper_cutout.paper_cutout_filter_xml(
            (track, clip),
            points=points_tuple,
            feather=feather,
            feather_passes=feather_passes,
            alpha_operation=alpha_operation,
            edge_scale=edge_scale,
            frame_width=width,
            frame_height=height,
            distort_amplitude=distort_amplitude,
            distort_frequency=distort_frequency,
            drop_shadow=drop_shadow,
            shadow_offset=shadow_offset,
            shadow_blur=shadow_blur,
            shadow_color=shadow_color,
        )
    except (ValueError, TypeError) as exc:
        return from_exception(exc)

    try:
        existing = patcher.list_effects(project, (track, clip))
    except (IndexError, ValueError) as exc:
        return from_exception(exc)
    first_effect_index = len(existing)

    inserted = 0
    for xml in xmls:
        try:
            patcher.insert_effect_xml(
                project, (track, clip), xml, position=first_effect_index + inserted
            )
        except (IndexError, ValueError) as exc:
            return operation_failed(f"partial failure after {inserted} filters", cause=exc, suggestion="A filter could not be inserted mid-chain. Restore a snapshot and retry with a valid track/clip.")
        inserted += 1

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "used_procedural_polygon": not bool(points_tuple),
        "edge_scale": float(edge_scale),
        "drop_shadow": bool(drop_shadow),
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_scifi_greenscreen(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    key_color: str = "#00FF00",
    tolerance_near: float = 0.10,
    tolerance_far: float = 0.20,
    edge_smooth: float = 0.05,
    spill_correction: bool = True,
    spill_target_color: str = "#C87F65",
    spill_tolerance: float = 0.24,
    spill_slope: float = 0.4,
    spill_two_pass: bool = True,
    despill: bool = True,
    despill_amount: float = 0.05,
    despill_brightness: float = 0.0,
) -> dict:
    """Apply the tutorial's full sci-fi green-screen keying stack in one snapshot.

    Reproduces the ordered three-effect green-screen recipe from the
    Photolearningism tutorial *"Sci-Fi Effects | Mastering Chroma Keying in
    KDEnlive"* (video ``uqge5McjO7E``). Filters are appended to the clip's stack
    in this load-bearing order (the tutorial stresses processing order at
    ``[07:42]``):

    1. ``frei0r.keyspillm0pup`` -- **Key Spill Mop Up**, *first*, so the green
       bounce is corrected on the subject **before** the key removes the
       backdrop (``[05:24]``). Skipped when ``spill_correction=False``.
    2. ``avfilter.hsvkey`` -- **Chroma Key: Advanced**, the actual key
       (``[02:20]``). Built by reusing
       :func:`masking.build_chroma_key_advanced_xml`, the same pipeline function
       backing ``effect_chroma_key_advanced``.
    3. ``avfilter.despill`` -- **Despill**, *last*, restoring the brightness /
       detail the key stripped off the subject (``[08:28]``). Skipped when
       ``despill=False``.

    Parameters
    ----------
    key_color:
        Green-screen color to key out. Drives the advanced key, the Key-Spill
        key color, and the green/blue screen type of both spill filters.
    tolerance_near, tolerance_far, edge_smooth:
        Advanced-key (``hsvkey``) similarity / blend controls (``tolerance_far``
        must be >= ``tolerance_near``).
    spill_correction, spill_target_color, spill_tolerance, spill_slope,
    spill_two_pass:
        Key-Spill-Mop-Up controls. ``spill_target_color`` is the hue "borrowed
        from the hand" to repaint the spill; ``spill_two_pass`` enables the
        second De-Key pass the tutorial recommends.
    despill, despill_amount, despill_brightness:
        Despill restore controls (``av.mix`` and ``av.brightness``).

    **Omitted sub-effects (not taught in *this* video and/or unsupported by
    current primitives; documented in
    docs/research/2026-07-03-tutorial-effect-analysis/scifi-chroma-key.md):**

    * Background-plate replacement / compositing -- the tutorial reveals the
      track below purely by keying, never placing or grading a plate. Put a
      plate on a lower track and use ``composite_set`` separately if wanted.
    * Plate grading, glow, and atmosphere -- absent from this tutorial.
    * Animated / keyframed keying -- the tutorial demonstrates a single static
      key; the rotoscoping primitive only emits a frame-0 spline anyway.
    * The Position-and-Zoom crop -- clip-specific framing, not part of the recipe.

    **Known issue:** clip filters currently attach at the MLT root rather than
    nested in the playlist ``<entry>`` (§1.1/§1.2 of
    docs/plans/2026-07-03-kdenlive-mcp-improvements.md); this tool inherits that
    placement behaviour until the fix lands.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import masking
    from workshop_video_brain.edit_mcp.pipelines import scifi_greenscreen as _sg
    from workshop_video_brain.workspace import create_snapshot

    if tolerance_far < tolerance_near:
        return _err("tolerance_far must be >= tolerance_near")

    # Validate all colors up front (clear message, no snapshot on failure).
    try:
        masking.color_to_mlt_hex(key_color)
        if spill_correction:
            masking.color_to_mlt_hex(spill_target_color)
    except ValueError:
        return _err(_VALID_COLOR_FORMATS_MSG)

    # Build the tuneable param dicts (also validates numeric ranges).
    try:
        keyspill = (
            _sg.keyspill_mopup_params(
                key_color=key_color,
                target_color=spill_target_color,
                tolerance=spill_tolerance,
                slope=spill_slope,
                two_pass=spill_two_pass,
            )
            if spill_correction
            else None
        )
        despill_p = (
            _sg.despill_params(
                key_color=key_color,
                amount=despill_amount,
                brightness=despill_brightness,
            )
            if despill
            else None
        )
    except ValueError as exc:
        return from_exception(exc)

    services = _sg.scifi_greenscreen_services(
        spill_correction=spill_correction, despill=despill
    )
    # Verify every service resolves in the catalog up front.
    for svc in services:
        kid, _eff = _lookup_catalog_by_service(svc)
        if kid is None:
            return _err(f"missing catalog service: {svc}")

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    # Single snapshot before writing.
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_scifi_greenscreen"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)
    try:
        existing = patcher.list_effects(project, (track, clip))
    except (IndexError, ValueError) as exc:
        return from_exception(exc)
    first_effect_index = len(existing)

    # Build the ordered XML for each filter. The advanced key reuses the
    # masking pipeline function (same one behind effect_chroma_key_advanced).
    xml_by_service: dict[str, str] = {}
    if keyspill is not None:
        xml_by_service[_sg.KEYSPILL_SERVICE] = _build_filter_xml(
            mlt_service=_sg.KEYSPILL_SERVICE,
            kdenlive_id=_sg.KEYSPILL_KID,
            track=track,
            clip=clip,
            props=list(keyspill.items()),
        )
    try:
        xml_by_service[_sg.KEY_SERVICE] = masking.build_chroma_key_advanced_xml(
            (track, clip), key_color, tolerance_near, tolerance_far, edge_smooth,
        )
    except (ValueError, IndexError) as exc:
        return from_exception(exc)
    if despill_p is not None:
        xml_by_service[_sg.DESPILL_SERVICE] = _build_filter_xml(
            mlt_service=_sg.DESPILL_SERVICE,
            kdenlive_id=_sg.DESPILL_KID,
            track=track,
            clip=clip,
            props=list(despill_p.items()),
        )

    inserted = 0
    for svc in services:
        try:
            patcher.insert_effect_xml(
                project, (track, clip), xml_by_service[svc],
                position=first_effect_index + inserted,
            )
        except (IndexError, ValueError) as exc:
            return operation_failed(f"partial failure after {inserted} filters", cause=exc, suggestion="A filter could not be inserted mid-chain. Restore a snapshot and retry with a valid track/clip.")
        inserted += 1

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "services": services,
        "key_color": key_color,
        "screen_type": _sg.screen_type_from_color(key_color),
        "snapshot_id": snapshot_id,
    })
