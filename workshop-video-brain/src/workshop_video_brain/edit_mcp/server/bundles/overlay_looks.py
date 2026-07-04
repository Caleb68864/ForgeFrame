"""Additive-overlay *look* bundle tools: ``effect_light_leak`` + ``effect_day_to_night``.

Two tutorial-derived looks that share the **additive-overlay** pattern -- a
second clip on a track above the base footage, composited with a lightening
blend mode (Screen / Lighten / Add):

* ``effect_light_leak`` -- Fabiano's *"Using Screen/Lighten Blend mode
  transition to include light leaks in KDENLIVE"* (``-3TjF3OzECc``).
* ``effect_day_to_night`` -- the kdenlivetutorials.com *"From Day to Night"*
  blog: a hue/saturation/levels grade toward night with an optional sky overlay.

Analysis + honest-subset omissions:
``docs/research/2026-07-03-tutorial-effect-analysis/lightleak-daynight.md``.
Pure logic lives in ``pipelines/overlay_looks.py``; this module does the
snapshot + XML I/O and returns the ``_ok`` / ``_err`` envelopes.

Registered by the ``bundles`` package auto-importer.
"""
from __future__ import annotations

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
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
)


def _resolve_video_clip(project, track: int, clip: int):
    """Return (playlist, real_entries, duration_frames) or raise ValueError."""
    from workshop_video_brain.edit_mcp.pipelines.overlay_looks import video_playlists

    vps = video_playlists(project)
    if not vps:
        raise ValueError("No video playlists found in project")
    if track < 0 or track >= len(vps):
        raise ValueError(
            f"track index {track} out of range "
            f"(project has {len(vps)} video track(s))"
        )
    playlist = vps[track]
    real = [e for e in playlist.entries if e.producer_id]
    if not real:
        raise ValueError(f"Playlist '{playlist.id}' has no clips")
    if clip < 0 or clip >= len(real):
        raise ValueError(
            f"clip_index {clip} out of range (playlist has {len(real)} clip(s))"
        )
    entry = real[clip]
    return playlist, real, entry.out_point - entry.in_point + 1


@mcp.tool()
@tool_guard
def effect_light_leak(
    workspace_path: str,
    project_file: str,
    leak_media: str,
    target_track: int,
    at_frame: int,
    overlay_track: int = -1,
    blend_mode: str = "screen",
    opacity: float = 1.0,
    fade_in_frames: int = 0,
    fade_out_frames: int = 0,
    duration_frames: int = 120,
) -> dict:
    """Overlay a light-leak clip above the footage and blend it additively.

    Reproduces Fabiano's *"Using Screen/Lighten Blend mode transition to include
    light leaks in KDENLIVE"* tutorial (``-3TjF3OzECc``): the light-leak /
    lens-flare clip is laid on a track *above* the base footage and composited
    with a lightening blend mode so only its bright parts show through.

    Args:
        leak_media: Path to the light-leak / lens-flare clip.
        target_track: Video-track index of the base footage (the layer below).
        at_frame: Frame on the overlay track where the leak starts.
        overlay_track: Video-track index for the leak. ``-1`` => ``target_track
            + 1`` (a track above the footage; it must already exist -- add one
            with ``track_add`` first).
        blend_mode: One of ``screen`` (default), ``lighten``, ``add``.
        opacity: ``[0.0, 1.0]`` -- composite opacity (mapped to geometry 0..100).
        fade_in_frames / fade_out_frames: optional keyframed opacity fades on the
            leak clip (``affine``/``transform`` filter).
        duration_frames: length of the leak clip on the timeline (frames).

    Honest-subset / known-issue notes (see the analysis report): composite-track
    semantics and filter placement are the shared §1.1/§1.2 open issue
    (docs/plans/2026-07-03-kdenlive-mcp-improvements.md) -- not a blocker for
    building the look.
    """
    from pathlib import Path

    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.compositing import apply_composite
    from workshop_video_brain.edit_mcp.pipelines.effect_presets import build_fade_keyframes
    from workshop_video_brain.edit_mcp.pipelines import keyframes as _kf
    from workshop_video_brain.edit_mcp.pipelines.overlay_looks import (
        LIGHT_LEAK_BLEND_MODES,
        build_filter_xml,
        insert_overlay_clip,
        lookup_catalog_id,
        overlay_geometry,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
    if not leak_media or not str(leak_media).strip():
        return err("leak_media must be a non-empty path", suggestion="Pass the path to the light-leak clip to overlay; it resolves under the workspace root unless absolute.")
    if not Path(leak_media).exists():
        return err(f"leak_media does not exist: {leak_media}", suggestion="Check the leak_media path; it resolves under the workspace root unless absolute.")
    if blend_mode not in LIGHT_LEAK_BLEND_MODES:
        return err(
            f"Unknown blend_mode '{blend_mode}'; light-leak modes: "
            f"{sorted(LIGHT_LEAK_BLEND_MODES)}",
            suggestion="Pass blend_mode as one of the listed light-leak modes (e.g. 'screen' or 'add').",
        )
    if at_frame < 0:
        return err("at_frame must be >= 0", suggestion="Pass at_frame as 0 or more (the frame where the overlay starts).")
    if duration_frames <= 0:
        return err("duration_frames must be > 0", suggestion="Pass a positive duration_frames for how long the overlay lasts.")
    if fade_in_frames < 0 or fade_out_frames < 0:
        return err("fade frames must be >= 0", suggestion="Pass fade_in/fade_out frame counts as 0 or more.")
    if not 0.0 <= float(opacity) <= 1.0:
        return err(f"opacity must be in [0.0, 1.0]; got {opacity}", suggestion="Pass opacity as a fraction between 0.0 (invisible) and 1.0 (solid).")

    resolved_overlay = overlay_track if overlay_track >= 0 else target_track + 1
    if resolved_overlay == target_track:
        return err("overlay_track must differ from target_track", suggestion="Put the overlay on a different track from the footage it sits over; pass a distinct overlay_track index.")

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_light_leak"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    project = parse_project(project_path)
    fps = project.profile.fps or 25.0
    width, height = project.profile.width, project.profile.height

    # 1. Model-level insert of the leak clip on the overlay track.
    try:
        overlay_clip_index = insert_overlay_clip(
            project, resolved_overlay, leak_media, at_frame, duration_frames
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # 2. Optional keyframed opacity fades on the leak clip.
    fade_effect_index = None
    if fade_in_frames > 0 or fade_out_frames > 0:
        try:
            raw = build_fade_keyframes(
                fade_in_frames=fade_in_frames,
                fade_out_frames=fade_out_frames,
                clip_duration_frames=duration_frames,
                fps=fps,
            )
            rekeyed = [
                _kf.Keyframe(
                    frame=kf.frame,
                    value=(0, 0, width, height, float(kf.value[4])),
                    easing=kf.easing,
                )
                for kf in raw
            ]
            rect_str = _kf.build_keyframe_string("rect", rekeyed, fps=fps)
        except ValueError as exc:
            return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
        kid = lookup_catalog_id("affine") or "transform"
        xml = build_filter_xml(
            mlt_service="affine",
            kdenlive_id=kid,
            track=resolved_overlay,
            clip=overlay_clip_index,
            props=[("rect", rect_str)],
        )
        try:
            existing = patcher.list_effects(project, (resolved_overlay, overlay_clip_index))
            fade_effect_index = len(existing)
            patcher.insert_effect_xml(
                project, (resolved_overlay, overlay_clip_index), xml,
                position=fade_effect_index,
            )
        except (IndexError, ValueError) as exc:
            return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # 3. Composite the overlay onto the base with a lightening blend mode.
    end_frame = at_frame + duration_frames - 1
    try:
        updated = apply_composite(
            project,
            track_a=target_track,
            track_b=resolved_overlay,
            start_frame=at_frame,
            end_frame=end_frame,
            blend_mode=blend_mode,
            geometry=overlay_geometry(width, height, opacity),
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(updated, project_path)
    return _ok({
        "leak_media": str(leak_media),
        "target_track": target_track,
        "overlay_track": resolved_overlay,
        "overlay_clip_index": overlay_clip_index,
        "blend_mode": blend_mode,
        "opacity": float(opacity),
        "at_frame": at_frame,
        "end_frame": end_frame,
        "fade_effect_index": fade_effect_index,
        "composition_added": True,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_day_to_night(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    intensity: float = 0.5,
    sky_media: str = "",
    keyframed: bool = True,
    blend_mode: str = "screen",
    overlay_track: int = -1,
    sky_at_frame: int = 0,
    sky_duration_frames: int = 120,
) -> dict:
    """Grade a clip from day toward night, with an optional sky overlay.

    Reproduces the achievable subset of the kdenlivetutorials.com *"From Day to
    Night"* blog: a hue/saturation/levels grade that darkens and blue-shifts the
    plate toward night. Two filters are appended in one snapshot:

    1. ``avfilter.eq`` -- darken (brightness), desaturate, mild contrast
       (the blog's Levels-darken + Saturation).
    2. ``frei0r.colorize`` -- a blue night tint (the blog's Hue-toward-blue).

    When ``keyframed`` is true, the animated parameters ramp from a neutral day
    at frame 0 to full night at the clip's last frame, so the shot visibly turns
    to night over its length; otherwise static night values are written.

    Args:
        track: Video-track index of the clip to grade.
        clip_index: Clip index within that track.
        intensity: ``[0.0, 1.0]`` -- how far to push toward night.
        sky_media: Optional starry-sky clip. When given, it is composited on a
            track above via the shared additive overlay helper (Screen/Lighten/
            Add), reusing ``effect_light_leak``'s insert+blend path.
        keyframed: Ramp the grade day->night across the clip (default true).
        blend_mode: Sky composite blend mode (``screen`` default / ``lighten`` /
            ``add``).
        overlay_track: Track for the sky. ``-1`` => ``track + 1``.
        sky_at_frame / sky_duration_frames: sky overlay placement + length.

    Honest-subset omission (see the analysis report): the blog's final
    distance-brightness stage keeps foreground objects bright with an *animated*
    Rotoscoping mask + Curves. Per-frame roto is a known hard blocker
    (``masking._spline_json`` emits frame 0 only), so the whole-frame grade
    ships and the roto-scoped brightening does not. Filter placement is the
    shared §1.1/§1.2 open issue.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.compositing import apply_composite
    from workshop_video_brain.edit_mcp.pipelines.overlay_looks import (
        LIGHT_LEAK_BLEND_MODES,
        DAY_TO_NIGHT_SERVICES,
        build_filter_xml,
        day_to_night_chain,
        insert_overlay_clip,
        lookup_catalog_id,
        overlay_geometry,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
    if not 0.0 <= float(intensity) <= 1.0:
        return err(f"intensity must be in [0.0, 1.0]; got {intensity}", suggestion="Pass intensity as a fraction between 0.0 (off) and 1.0 (full).")

    use_sky = bool(sky_media and str(sky_media).strip())
    if use_sky:
        from pathlib import Path as _Path

        if not _Path(sky_media).exists():
            return err(f"sky_media does not exist: {sky_media}", suggestion="Check the sky_media path; it resolves under the workspace root unless absolute.")
        if blend_mode not in LIGHT_LEAK_BLEND_MODES:
            return err(
                f"Unknown blend_mode '{blend_mode}'; sky overlay modes: "
                f"{sorted(LIGHT_LEAK_BLEND_MODES)}",
                suggestion="Pass blend_mode as one of the listed sky-overlay modes (e.g. 'screen' or 'add').",
            )

    project = parse_project(project_path)
    fps = project.profile.fps or 25.0
    width, height = project.profile.width, project.profile.height

    try:
        _pl, _real, duration = _resolve_video_clip(project, track, clip_index)
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    resolved_overlay = overlay_track if overlay_track >= 0 else track + 1

    try:
        chain = day_to_night_chain(
            intensity=intensity,
            keyframed=keyframed,
            duration_frames=duration,
            fps=fps,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Verify every service resolves in the catalog up front.
    resolved: list[tuple[str, str, dict[str, str]]] = []
    for svc in DAY_TO_NIGHT_SERVICES:
        kid = lookup_catalog_id(svc)
        if kid is None:
            return err(f"Effect service '{svc}' is not in the generated catalog.", suggestion="Regenerate the catalog with `uv run workshop-video-brain catalog regenerate`, or use effect_list_common to pick a known effect.")
        props = dict(next(p for s, p in chain if s == svc))
        resolved.append((svc, kid, props))

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_day_to_night"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    # Grade filters onto the target clip.
    try:
        existing = patcher.list_effects(project, (track, clip_index))
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    first_effect_index = len(existing)

    inserted = 0
    for svc, kid, props in resolved:
        xml = build_filter_xml(
            mlt_service=svc,
            kdenlive_id=kid,
            track=track,
            clip=clip_index,
            props=[(k, v) for k, v in props.items()],
        )
        try:
            patcher.insert_effect_xml(
                project, (track, clip_index), xml,
                position=first_effect_index + inserted,
            )
        except (IndexError, ValueError) as exc:
            return err(f"partial failure after {inserted} filters: {exc}", suggestion="Some filters applied before this one failed. Restore the pre-op snapshot with snapshot_restore, then retry.")
        inserted += 1

    # Optional sky overlay: same additive insert + blend path as light-leak.
    sky_info = None
    final_project = project
    if use_sky:
        try:
            sky_clip_index = insert_overlay_clip(
                project, resolved_overlay, sky_media, sky_at_frame, sky_duration_frames
            )
            sky_end = sky_at_frame + sky_duration_frames - 1
            final_project = apply_composite(
                project,
                track_a=track,
                track_b=resolved_overlay,
                start_frame=sky_at_frame,
                end_frame=sky_end,
                blend_mode=blend_mode,
                geometry=overlay_geometry(width, height, 1.0),
            )
            sky_info = {
                "sky_media": str(sky_media),
                "overlay_track": resolved_overlay,
                "sky_clip_index": sky_clip_index,
                "blend_mode": blend_mode,
                "at_frame": sky_at_frame,
                "end_frame": sky_end,
            }
        except ValueError as exc:
            return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(final_project, project_path)
    return _ok({
        "first_effect_index": first_effect_index,
        "filter_count": inserted,
        "services": [svc for svc, _, _ in resolved],
        "intensity": float(intensity),
        "keyframed": bool(keyframed),
        "duration_frames": duration,
        "sky": sky_info,
        "snapshot_id": snapshot_id,
    })
