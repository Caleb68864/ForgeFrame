"""Creative effect bundles (glitch/hologram/fade/flash) and reorder wrappers.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

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
    _resolve_playlist,
    _build_filter_xml,
    _lookup_catalog_by_service,
)



def _playlist_clip_duration_frames(playlist, clip_index: int) -> int:
    """Return duration (frames) of the ``clip_index``th real entry."""
    real = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real):
        raise IndexError(
            f"clip_index {clip_index} out of range (playlist has {len(real)} clips)"
        )
    entry = real[clip_index]
    return entry.out_point - entry.in_point + 1


@mcp.tool()
@tool_guard
def effect_glitch_stack(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    intensity: float = 0.5,
) -> dict:
    """Append a 5-filter glitch stack to a clip in one snapshot.

    Filters inserted in this order: ``frei0r.pixeliz0r``, ``frei0r.glitch0r``,
    ``frei0r.rgbsplit0r``, ``frei0r.scanline0r``, ``avfilter.exposure``.

    ``intensity`` scales per-filter tuneable parameters in ``[0.0, 1.0]``.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.effect_presets import (
        GLITCH_SERVICES,
        glitch_stack_params,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        stack = glitch_stack_params(intensity)
    except ValueError as exc:
        return from_exception(exc)

    # Verify every service is in the catalog up front.
    resolved: list[tuple[str, str, dict[str, str]]] = []
    for svc in GLITCH_SERVICES:
        kid, eff = _lookup_catalog_by_service(svc)
        if kid is None:
            return _err(f"missing catalog service: {svc}")
        params = dict(next(p for s, p in stack if s == svc))
        resolved.append((svc, kid, params))

    # Single snapshot
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_glitch_stack"
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
            return _err(
                f"partial failure after {inserted} filters: {exc}"
            )
        inserted += 1

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "intensity": float(intensity),
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_hologram(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    tint_color: str = "#33ccff",
    scanline_intensity: float = 0.5,
    glow: float = 0.35,
    transparency: float = 0.25,
    flicker: float = 0.3,
    start_frame: int = 0,
    end_frame: int = -1,
) -> dict:
    """Apply the tutorial's full hologram *look* to a clip in one snapshot.

    Composes an ordered stack of clip filters that reproduces the achievable
    "look" layer of the Photolearningism *"How to Create Realistic Holograms in
    KDENlive"* VFX tutorial (video ``P0eI7YLN3FU``):

    * ``frei0r.colorize`` -- the tutorial's **Colorize** ("I like it blue"),
      hue/saturation derived from ``tint_color`` (default hologram cyan).
    * ``frei0r.scanline0r`` -- interlaced hologram scan lines (added when
      ``scanline_intensity`` > 0; the service has no tuneable parameters).
    * ``boxblur`` -- the tutorial's one-axis **Box Blur** ("interrupted
      transmission effect"), scaled horizontally by ``scanline_intensity``.
    * ``frei0r.glow`` -- hologram bloom, scaled by ``glow``.
    * ``frei0r.glitch0r`` -- hologram **flicker**; when ``end_frame`` >
      ``start_frame`` the Glitch Frequency is animated across the window,
      otherwise a static value is used. Scaled by ``flicker``.
    * ``frei0r.transparency`` -- the tutorial's **Transparency** (translucency);
      ``transparency`` is the fraction of visibility removed (0 = opaque).

    All intensity parameters are in ``[0.0, 1.0]``. ``end_frame`` defaults to
    the end of the clip (``-1`` sentinel).

    **Omitted sub-effects (not reproducible with current primitives; documented
    in docs/research/2026-07-03-tutorial-effect-analysis/hologram-effect.md):**

    * Green-screen isolation (advanced chroma key + key-spill mop-up) and
      rotoscoping to a single subject -- the rotoscoping primitive emits only a
      frame-0 spline, so the animated mask the tutorial draws around a moving
      subject is not achievable.
    * Motion tracking (``opencv.tracker``) → copy-keyframes → **Transform**
      import, which locks the hologram to the on-screen projector. No motion
      tracker exists in the catalog, so the hologram is applied to the whole
      frame rather than a tracked region.
    * The extra "white splotches / projection backing" overlay layers.

    **Known issue:** clip filters currently attach at the MLT root rather than
    nested in the playlist ``<entry>`` (§1.1 of
    docs/plans/2026-07-03-kdenlive-mcp-improvements.md); this tool inherits that
    placement behaviour until the fix lands.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.hologram import hologram_stack_params
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    project = parse_project(project_path)
    fps = project.profile.fps or 25.0

    # Resolve the flicker window (default -1 => end of clip).
    try:
        playlist = _resolve_playlist(project, track)
        duration = _playlist_clip_duration_frames(playlist, clip)
    except (ValueError, IndexError) as exc:
        return from_exception(exc)
    resolved_end = end_frame
    if resolved_end < 0:
        resolved_end = duration - 1

    try:
        stack = hologram_stack_params(
            tint_color=tint_color,
            scanline_intensity=scanline_intensity,
            glow=glow,
            transparency=transparency,
            flicker=flicker,
            start_frame=start_frame,
            end_frame=resolved_end,
            fps=fps,
        )
    except ValueError as exc:
        return from_exception(exc)

    # Verify every service resolves in the catalog up front.
    resolved: list[tuple[str, str, dict[str, str]]] = []
    for svc, params in stack:
        kid, _eff = _lookup_catalog_by_service(svc)
        if kid is None:
            return _err(f"missing catalog service: {svc}")
        resolved.append((svc, kid, params))

    # Single snapshot before writing.
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_hologram"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

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
            return _err(f"partial failure after {inserted} filters: {exc}")
        inserted += 1

    serialize_project(project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "services": [svc for svc, _, _ in resolved],
        "tint_color": tint_color,
        "start_frame": start_frame,
        "end_frame": resolved_end,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_fade(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    fade_in_frames: int = 0,
    fade_out_frames: int = 0,
    easing: str = "ease_in_out",
) -> dict:
    """Append a keyframed ``transform`` fade filter (opacity) to a clip.

    At least one of ``fade_in_frames`` / ``fade_out_frames`` must be > 0.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import keyframes as _kf
    from workshop_video_brain.edit_mcp.pipelines.effect_presets import (
        build_fade_keyframes,
    )
    from workshop_video_brain.workspace import create_snapshot

    if fade_in_frames == 0 and fade_out_frames == 0:
        return _err("at least one fade must be non-zero")
    if fade_in_frames < 0 or fade_out_frames < 0:
        return _err("fade frames must be >= 0")

    # Validate easing early (matches resolve_easing errors)
    try:
        _kf.resolve_easing(easing)
    except ValueError as exc:
        return from_exception(exc)

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    # Snapshot first (single)
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_fade"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)
    fps = project.profile.fps or 25.0
    width = project.profile.width
    height = project.profile.height

    try:
        playlist = _resolve_playlist(project, track)
        duration = _playlist_clip_duration_frames(playlist, clip)
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    try:
        raw_keyframes = build_fade_keyframes(
            fade_in_frames=fade_in_frames,
            fade_out_frames=fade_out_frames,
            clip_duration_frames=duration,
            fps=fps,
            easing=easing,
        )
    except ValueError as exc:
        return from_exception(exc)

    # Rebuild with proper rect dimensions (0 0 W H opacity).
    rekeyed = [
        _kf.Keyframe(
            frame=kf.frame,
            value=(0, 0, width, height, float(kf.value[4])),
            easing=kf.easing,
        )
        for kf in raw_keyframes
    ]
    try:
        rect_str = _kf.build_keyframe_string("rect", rekeyed, fps=fps)
    except ValueError as exc:
        return from_exception(exc)

    xml = _build_filter_xml(
        mlt_service="affine",
        kdenlive_id="transform",
        track=track,
        clip=clip,
        props=[("rect", rect_str)],
    )

    try:
        existing = patcher.list_effects(project, (track, clip))
        position = len(existing)
        patcher.insert_effect_xml(project, (track, clip), xml, position=position)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({
        "effect_index": position,
        "keyframe_count": len(rekeyed),
        "fade_in_frames": fade_in_frames,
        "fade_out_frames": fade_out_frames,
        "easing": easing,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def flash_cut_montage(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    n_cuts: int = 4,
    blur_amount: float = 30.0,
    invert_alt: bool = True,
) -> dict:
    """Split a clip into ``n_cuts`` pieces and apply rotating directional blur.

    If ``invert_alt`` is true, every other piece also receives an
    ``avfilter.negate`` filter (indices 1, 3, ...).
    """
    from workshop_video_brain.core.models.timeline import SplitClip
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.effect_presets import (
        montage_split_offsets,
    )
    from workshop_video_brain.workspace import create_snapshot

    if n_cuts < 2:
        return _err(f"n_cuts must be >= 2; got {n_cuts}")

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    # Verify effects present in catalog
    blur_kid, _ = _lookup_catalog_by_service("avfilter.dblur")
    if blur_kid is None:
        return _err("missing catalog service: avfilter.dblur")
    neg_kid, _ = _lookup_catalog_by_service("avfilter.negate")
    if invert_alt and neg_kid is None:
        return _err("missing catalog service: avfilter.negate")

    # Snapshot ONCE before anything
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_flash_cut_montage"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)

    try:
        playlist = _resolve_playlist(project, track)
        duration = _playlist_clip_duration_frames(playlist, clip)
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    try:
        offsets = montage_split_offsets(n_cuts, duration)
    except ValueError as exc:
        return from_exception(exc)

    # Perform splits from the RIGHTMOST offset to the leftmost so that
    # the clip at index `clip` keeps the same index during successive splits.
    # After each split at offset o on the original clip, the left half stays
    # at `clip` with the same in_point (so the next leftward offset is still
    # measured from the same in_point relative to the clip in-point).
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher as _pp
    intents_sequential = []
    for off in sorted(offsets, reverse=True):
        intent = SplitClip(
            track_ref=playlist.id,
            clip_index=clip,
            split_at_frame=off,
        )
        intents_sequential.append(intent)

    try:
        project = _pp.patch_project(project, intents_sequential)
    except Exception as exc:  # noqa: BLE001
        return _err(f"split failed: {exc}")

    # Re-resolve playlist after patch (patch_project returns a new project).
    playlist = _resolve_playlist(project, track)
    # The pieces live at consecutive indices [clip, clip+1, ..., clip+n_cuts-1].
    piece_indices = [clip + i for i in range(n_cuts)]

    inserted_filters = 0
    for i, piece_idx in enumerate(piece_indices):
        angle = (i * 360.0 / n_cuts) % 360.0
        xml_blur = _build_filter_xml(
            mlt_service="avfilter.dblur",
            kdenlive_id=blur_kid,
            track=track,
            clip=piece_idx,
            props=[
                ("av.angle", f"{angle}"),
                ("av.radius", f"{float(blur_amount)}"),
            ],
        )
        try:
            existing = patcher.list_effects(project, (track, piece_idx))
            pos = len(existing)
            patcher.insert_effect_xml(
                project, (track, piece_idx), xml_blur, position=pos
            )
            inserted_filters += 1
        except (IndexError, ValueError) as exc:
            return _err(
                f"partial failure inserting blur on piece {i}: {exc}"
            )

        if invert_alt and (i % 2 == 1):
            xml_neg = _build_filter_xml(
                mlt_service="avfilter.negate",
                kdenlive_id=neg_kid,
                track=track,
                clip=piece_idx,
                props=[],
            )
            try:
                existing = patcher.list_effects(project, (track, piece_idx))
                pos = len(existing)
                patcher.insert_effect_xml(
                    project, (track, piece_idx), xml_neg, position=pos
                )
                inserted_filters += 1
            except (IndexError, ValueError) as exc:
                return _err(
                    f"partial failure inserting negate on piece {i}: {exc}"
                )

    serialize_project(project, project_path)
    return _ok({
        "split_clip_indices": piece_indices,
        "filter_count": inserted_filters,
        "n_cuts": n_cuts,
        "blur_amount": float(blur_amount),
        "invert_alt": invert_alt,
        "snapshot_id": snapshot_id,
    })




# ---------------------------------------------------------------------------
# Semantic reorder wrappers (move_to_top / move_to_bottom / move_up / move_down)
# ---------------------------------------------------------------------------
def _reorder_impl(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
    compute_to,
    noop_note: str,
    snapshot_description: str,
) -> dict:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        project = parse_project(project_path)
        stack_len = len(patcher.list_effects(project, (track, clip)))
    except (ValueError, IndexError, KeyError) as exc:
        return from_exception(exc)

    if effect_index < 0 or effect_index >= stack_len:
        return _err(
            f"effect_index {effect_index} out of range "
            f"(stack has {stack_len} filters)"
        )

    new_index = compute_to(effect_index, stack_len)
    if new_index is None:
        return _ok({
            "effect_index_before": effect_index,
            "effect_index_after": effect_index,
            "note": noop_note,
            "snapshot_id": None,
        })

    try:
        record = create_snapshot(
            ws_path, project_path, description=snapshot_description
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:
        return _err(f"Snapshot failed: {exc}")

    try:
        patcher.reorder_effects(project, (track, clip), effect_index, new_index)
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({
        "effect_index_before": effect_index,
        "effect_index_after": new_index,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def move_to_top(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
) -> dict:
    """Move a filter to the top (index 0) of a clip's filter stack."""
    return _reorder_impl(
        workspace_path, project_file, track, clip, effect_index,
        compute_to=lambda i, n: 0 if i > 0 else None,
        noop_note="already at top",
        snapshot_description="before_move_to_top",
    )


@mcp.tool()
@tool_guard
def move_to_bottom(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
) -> dict:
    """Move a filter to the bottom (last index) of a clip's filter stack."""
    return _reorder_impl(
        workspace_path, project_file, track, clip, effect_index,
        compute_to=lambda i, n: n - 1 if i < n - 1 else None,
        noop_note="already at bottom",
        snapshot_description="before_move_to_bottom",
    )


@mcp.tool()
@tool_guard
def move_up(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
) -> dict:
    """Move a filter up one position in a clip's filter stack."""
    return _reorder_impl(
        workspace_path, project_file, track, clip, effect_index,
        compute_to=lambda i, n: i - 1 if i > 0 else None,
        noop_note="already at top",
        snapshot_description="before_move_up",
    )


@mcp.tool()
@tool_guard
def move_down(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
) -> dict:
    """Move a filter down one position in a clip's filter stack."""
    return _reorder_impl(
        workspace_path, project_file, track, clip, effect_index,
        compute_to=lambda i, n: i + 1 if i < n - 1 else None,
        noop_note="already at bottom",
        snapshot_description="before_move_down",
    )
