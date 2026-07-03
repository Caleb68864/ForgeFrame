"""Bundle tool: ``transition_zoom_whip``.

Composes a zoom / whip-pan transition across a cut on a single video track:
a keyframed transform (scale) + directional-blur ramp out of the outgoing clip,
mirrored by a ramp into the incoming clip, with the directional blur peaking at
the cut. Derived from the Nuxttux "Zoom / Whip-Pan Transition" Kdenlive tutorial
(https://www.youtube.com/watch?v=ex7GoLFOnio).

Auto-imported by ``bundles/__init__.py``; registers via ``@mcp.tool()``.
Snapshot-before-write; returns ``_ok``/``_err`` dicts.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

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

from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import zoom_whip as _zw
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _require_workspace,
)
from workshop_video_brain.workspace import create_snapshot


def _filter_xml(
    service: str,
    kdenlive_id: str,
    track: int,
    clip_index: int,
    props: dict[str, str],
) -> str:
    """Serialize a root-level ``<filter>`` associated to (track, clip_index)."""
    filt = ET.Element(
        "filter",
        {"mlt_service": service, "track": str(track), "clip_index": str(clip_index)},
    )
    kid = ET.SubElement(filt, "property", {"name": "kdenlive_id"})
    kid.text = kdenlive_id
    for name, value in props.items():
        prop = ET.SubElement(filt, "property", {"name": name})
        prop.text = str(value)
    return ET.tostring(filt, encoding="unicode")


def _clip_frames(project, track: int, clip_index: int) -> int:
    """Frame length of a clip on a video track (out_point - in_point + 1)."""
    playlist = project.playlists[track]
    real = [e for e in playlist.entries if e.producer_id]
    entry = real[clip_index]
    return int(entry.out_point) - int(entry.in_point) + 1


@mcp.tool()
@tool_guard
def transition_zoom_whip(
    workspace_path: str,
    project_file: str,
    track: int,
    out_clip_index: int,
    in_clip_index: int,
    direction: str = "left",
    duration_frames: int = 12,
    zoom_amount: float = 1.4,
    blur: float = 6.0,
    easing: str = "cubic",
    pan_fraction: float = 0.75,
) -> dict:
    """Apply a zoom / whip-pan transition across a cut on one video track.

    Adds a keyframed Transform (scale punch) + directional-blur ramp to the
    outgoing clip (``out_clip_index``) and a mirrored ramp to the incoming clip
    (``in_clip_index``). The outgoing clip whip-pans off toward ``direction``
    while the blur ramps up to the cut; the incoming clip enters from the
    opposite side and settles to full frame as the blur ramps back down.

    Args:
        workspace_path: Absolute path to the workspace root.
        project_file: Project filename relative to the workspace root.
        track: Video track index (0 = first video track).
        out_clip_index: Zero-based index of the outgoing clip.
        in_clip_index: Zero-based index of the incoming clip.
        direction: Whip direction -- "left", "right", "up", or "down".
        duration_frames: Length of each half of the transition, in frames.
        zoom_amount: Peak scale multiplier at the cut (1.4 = 140%).
        blur: Peak directional-blur radius at the cut.
        easing: Ease family ("cubic") or non-directional name ("linear").
        pan_fraction: Fraction of available head-room used for the pan (0..1).

    Returns:
        Success dict with the effect indices and keyframe strings written to
        each clip, plus the snapshot id; or an error dict.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    if direction not in _zw.DIRECTIONS:
        return invalid_input(
            f"direction must be one of {sorted(_zw.DIRECTIONS)}; got {direction!r}",
            suggestion=f"Pass one of {sorted(_zw.DIRECTIONS)}.",
            given=direction,
        )

    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
        ProjectParseError,
    )
    try:
        project = parse_project(project_path)
    except ProjectParseError as exc:
        return corrupt_project(str(project_path), exc)

    # Resolve track / clip references up front for clear errors.
    n_tracks = len(project.playlists)
    if track < 0 or track >= n_tracks:
        return invalid_index("track", track, f"0..{n_tracks - 1}")
    real = [e for e in project.playlists[track].entries if e.producer_id]
    n_clips = len(real)
    for label, idx in (("out_clip_index", out_clip_index), ("in_clip_index", in_clip_index)):
        if idx < 0 or idx >= n_clips:
            return invalid_index(
                label, idx, f"0..{n_clips - 1}" if real else "no clips on this track"
            )

    fps = project.profile.fps
    width = project.profile.width
    height = project.profile.height

    try:
        plan = _zw.build_zoom_whip_plan(
            fps=fps,
            width=width,
            height=height,
            out_clip_frames=_clip_frames(project, track, out_clip_index),
            in_clip_frames=_clip_frames(project, track, in_clip_index),
            direction=direction,
            duration_frames=duration_frames,
            zoom_amount=zoom_amount,
            blur=blur,
            easing=easing,
            pan_fraction=pan_fraction,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Snapshot before any write.
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_transition_zoom_whip"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001 -- surface as error dict
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    written: dict[str, dict] = {}
    try:
        for role, clip_index in (("out", out_clip_index), ("in", in_clip_index)):
            half = plan[role]
            base = len(patcher.list_effects(project, (track, clip_index)))

            transform_xml = _filter_xml(
                _zw.TRANSFORM_SERVICE,
                _zw.TRANSFORM_KDENLIVE_ID,
                track,
                clip_index,
                {_zw.TRANSFORM_RECT_PROP: half["transform_rect"]},
            )
            patcher.insert_effect_xml(project, (track, clip_index), transform_xml, base)

            blur_xml = _filter_xml(
                _zw.DBLUR_SERVICE,
                _zw.DBLUR_KDENLIVE_ID,
                track,
                clip_index,
                {
                    _zw.DBLUR_ANGLE_PROP: half["blur_angle"],
                    _zw.DBLUR_RADIUS_PROP: half["blur_radius"],
                },
            )
            patcher.insert_effect_xml(project, (track, clip_index), blur_xml, base + 1)

            written[role] = {
                "clip_index": clip_index,
                "transform_effect_index": base,
                "blur_effect_index": base + 1,
                "transform_rect": half["transform_rect"],
                "blur_radius": half["blur_radius"],
                "blur_angle": half["blur_angle"],
                "start_frame": half["start_frame"],
                "end_frame": half["end_frame"],
            }
    except (IndexError, ValueError) as exc:
        return _err(f"Failed to build transition: {exc}")

    serialize_project(project, project_path)

    return _ok({
        "project_file": project_file,
        "track": track,
        "direction": direction,
        "duration_frames": duration_frames,
        "zoom_amount": zoom_amount,
        "blur": blur,
        "easing": easing,
        "snapshot_id": snapshot_id,
        "outgoing": written["out"],
        "incoming": written["in"],
    })
