"""Inspect, tweak, bypass and remove effects already applied to a clip.

Thin shells: parse -> validate -> patch (intents) -> snapshot -> serialize.
Logic lives in ``pipelines/effect_edit.py``; mutation in the
``SetEffectParams`` / ``SetEffectEnabled`` / ``RemoveEffect`` intents.
``track`` is the playlist index (as ``effect_add`` takes it); ``clip_index``
counts the clips on that track, blanks excluded.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    bad_json_param,
    corrupt_project,
    from_exception,
    invalid_index,
    invalid_input,
    missing_file,
    not_found,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _require_workspace

_KEYFRAME_HINT = (
    "This parameter is keyframed; edit it with effect_keyframe_set_scalar "
    "(numbers) or effect_keyframe_set_rect (rectangles) instead."
)


def _load(workspace_path: str, project_file: str, track: int, clip_index: int):
    """(ws_path, project_path, project, None) or (..., error dict)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import ProjectParseError, parse_project

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return None, None, None, from_exception(exc)
    if not project_file or not project_file.strip():
        return None, None, None, invalid_input(
            "project_file must be a non-empty string",
            "Pass the project path relative to the workspace, e.g. projects/working_copies/my_v3.kdenlive.",
            param="project_file")
    project_path = Path(project_file)
    if not project_path.is_absolute():
        project_path = ws_path / project_path
    if not project_path.exists():
        return None, None, None, missing_file(str(project_path), "project file")
    try:
        project = parse_project(project_path)
    except ProjectParseError as exc:
        return None, None, None, corrupt_project(str(project_path), exc)
    if track < 0 or track >= len(project.playlists):
        return None, None, None, invalid_index("track", track, f"0-{len(project.playlists) - 1}")
    clips = [e for e in project.playlists[track].entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(clips):
        return None, None, None, invalid_index(
            "clip", clip_index, f"0-{len(clips) - 1}" if clips else "none (the track is empty)")
    return ws_path, project_path, project, None


def _resolve(project, clip_ref, effect_index: int, effect_name: str):
    """(index, None) or (None, error dict)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
    from workshop_video_brain.edit_mcp.pipelines.effect_edit import resolve_effect_index

    try:
        return resolve_effect_index(project, clip_ref, effect_index, effect_name), None
    except IndexError:  # before LookupError: IndexError is a LookupError
        count = len(list_effects(project, clip_ref))
        return None, invalid_index("effect", effect_index, f"0-{count - 1}" if count else "none (the clip has no effects)")
    except LookupError as exc:
        return None, not_found("Effect", effect_name, hint=str(exc))
    except ValueError as exc:
        return None, invalid_input(str(exc), "Name the effect (effect_name) or give its stack position (effect_index), not both.")


def _describe(project, clip_ref, index: int) -> dict:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
    from workshop_video_brain.edit_mcp.pipelines.effect_edit import describe_effect

    return describe_effect(list_effects(project, clip_ref)[index])


def _write(ws_path: Path, project_path: Path, project, intents: list, label: str):
    """Patch, snapshot, save. (patched, snapshot_id, None) or (None, None, error)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    patched, report = patch_project(project, intents, with_report=True)
    if report.all_skipped:
        return None, None, invalid_input(
            "no changes applied: " + "; ".join(s["reason"] for s in report.skipped),
            "effect_list_applied shows the clip's effects and their positions.")
    try:
        snapshot_id = create_snapshot(ws_path, project_path, description=label).snapshot_id
    except Exception as exc:  # noqa: BLE001
        return None, None, operation_failed(f"Snapshot failed: {exc}", cause=exc,
                                            suggestion="Make sure the workspace is writable and has free space.")
    serialize_project(patched, project_path)
    return patched, snapshot_id, None


@mcp.tool()
@tool_guard
def effect_list_applied(workspace_path: str, project_file: str, track: int, clip_index: int) -> dict:
    """List the effects applied to a clip, in stack order, with their current values.

    Each effect reports ``index``, ``kdenlive_id``, ``mlt_service``, ``enabled``
    (false when bypassed with effect_toggle), ``static_params`` and
    ``keyframed_params`` (animated values: edit those with the keyframe tools).

    Args:
        workspace_path: Workspace root.
        project_file: Project path, relative to the workspace or absolute.
        track: Playlist index (as effect_add takes it).
        clip_index: Clip position on that track (blanks not counted).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
    from workshop_video_brain.edit_mcp.pipelines.effect_edit import describe_effect

    _ws, _path, project, problem = _load(workspace_path, project_file, track, clip_index)
    if problem:
        return problem
    effects = [describe_effect(row) for row in list_effects(project, (track, clip_index))]
    return _ok({"track": track, "clip_index": clip_index, "effects": effects, "count": len(effects)})


@mcp.tool()
@tool_guard
def effect_param_get(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    effect_index: int = -1,
    effect_name: str = "",
    param: str = "",
) -> dict:
    """Read an applied effect's parameters, or one parameter.

    Identify the effect by ``effect_index`` (stack position) or ``effect_name``
    (Kdenlive id or MLT service), not both. Empty ``param`` returns the whole
    description; otherwise ``{param, value, keyframed}``.
    """
    from workshop_video_brain.edit_mcp.pipelines.effect_edit import is_keyframed

    _ws, _path, project, problem = _load(workspace_path, project_file, track, clip_index)
    if problem:
        return problem
    clip_ref = (track, clip_index)
    index, problem = _resolve(project, clip_ref, effect_index, effect_name)
    if problem:
        return problem
    described = _describe(project, clip_ref, index)
    if not param:
        return _ok(described)
    values = {**described["static_params"], **described["keyframed_params"]}
    if param not in values:
        return not_found("Parameter", param,
                         hint="Parameters set on this effect: " + (", ".join(sorted(values)) or "(none)"))
    return _ok({"effect_index": index, "param": param, "value": values[param],
                "keyframed": is_keyframed(values[param])})


@mcp.tool()
@tool_guard
def effect_param_set(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    params: str,
    effect_index: int = -1,
    effect_name: str = "",
    force: bool = False,
) -> dict:
    """Change static parameters of an effect already applied to a clip.

    ``params`` is a JSON object, e.g. ``{"level": 0.3}``. Refused: the identity
    keys (mlt_service, kdenlive_id), ``disable`` (use effect_toggle), keyframed
    parameters (use the keyframe tools), and names the effect catalog does not
    list for this effect unless ``force=true``. Returns old and new values.
    """
    from workshop_video_brain.core.models.timeline import SetEffectParams
    from workshop_video_brain.edit_mcp.pipelines.effect_edit import (
        PROTECTED_PARAMS,
        check_param_names,
        is_keyframed,
        stringify,
    )

    try:
        requested = json.loads(params) if params and params.strip() else None
    except json.JSONDecodeError:
        return bad_json_param("params", '{"level": 0.3}', params)
    if not isinstance(requested, dict) or not requested:
        return invalid_input("params must be a non-empty JSON object",
                             'Pass name -> value pairs, e.g. {"level": 0.3}.', param="params")
    _ws, project_path, project, problem = _load(workspace_path, project_file, track, clip_index)
    if problem:
        return problem
    clip_ref = (track, clip_index)
    index, problem = _resolve(project, clip_ref, effect_index, effect_name)
    if problem:
        return problem
    described = _describe(project, clip_ref, index)

    protected = sorted(set(requested) & PROTECTED_PARAMS)
    if protected:
        hint = ("Use effect_toggle to switch an effect on or off." if "disable" in protected
                else "These identify the effect; remove it and add the one you want instead.")
        return invalid_input(f"Cannot set {', '.join(protected)} with effect_param_set", hint,
                             param="params", given=protected)
    keyframed = sorted(name for name in requested if name in described["keyframed_params"])
    if keyframed:
        return invalid_input(f"Keyframed parameter(s): {', '.join(keyframed)}", _KEYFRAME_HINT,
                             param="params", given=keyframed)
    unknown = check_param_names(described["kdenlive_id"], described["mlt_service"], requested)
    if unknown and not force:
        return invalid_input(
            f"{described['kdenlive_id'] or described['mlt_service']} has no catalogued parameter(s): "
            f"{', '.join(unknown)}",
            "Check the name with effect_info, or pass force=true to write it anyway.",
            param="params", given=unknown)

    values = {str(name): stringify(value) for name, value in requested.items()}
    for name, value in values.items():
        if is_keyframed(value):
            return invalid_input(f"Value for {name} looks like keyframes: {value}", _KEYFRAME_HINT, param="params")
    old = {name: {**described["static_params"]}.get(name) for name in values}
    _patched, snapshot_id, problem = _write(
        _ws, project_path, project,
        [SetEffectParams(track_index=track, clip_index=clip_index, effect_index=index, params=values)],
        f"before_effect_param_set_{index}")
    if problem:
        return problem
    return _ok({"effect_index": index, "kdenlive_id": described["kdenlive_id"],
                "mlt_service": described["mlt_service"], "old": old, "new": values,
                "snapshot_id": snapshot_id})


@mcp.tool()
@tool_guard
def effect_toggle(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    enabled: bool,
    effect_index: int = -1,
    effect_name: str = "",
) -> dict:
    """Bypass an applied effect (enabled=false) or switch it back on, without removing it.

    Writes the filter's ``disable`` property as Kdenlive's on/off switch does
    (1 = off, 0 = on); MLT skips a disabled filter when rendering.
    """
    from workshop_video_brain.core.models.timeline import SetEffectEnabled

    _ws, project_path, project, problem = _load(workspace_path, project_file, track, clip_index)
    if problem:
        return problem
    clip_ref = (track, clip_index)
    index, problem = _resolve(project, clip_ref, effect_index, effect_name)
    if problem:
        return problem
    before = _describe(project, clip_ref, index)
    _patched, snapshot_id, problem = _write(
        _ws, project_path, project,
        [SetEffectEnabled(track_index=track, clip_index=clip_index, effect_index=index, enabled=bool(enabled))],
        f"before_effect_toggle_{index}")
    if problem:
        return problem
    return _ok({"effect_index": index, "kdenlive_id": before["kdenlive_id"],
                "mlt_service": before["mlt_service"], "was_enabled": before["enabled"],
                "enabled": bool(enabled), "snapshot_id": snapshot_id})


@mcp.tool()
@tool_guard
def effect_remove(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    effect_index: int = -1,
    effect_name: str = "",
) -> dict:
    """Remove one effect from a clip's stack. Other effects and clips are untouched."""
    from workshop_video_brain.core.models.timeline import RemoveEffect
    from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects

    _ws, project_path, project, problem = _load(workspace_path, project_file, track, clip_index)
    if problem:
        return problem
    clip_ref = (track, clip_index)
    index, problem = _resolve(project, clip_ref, effect_index, effect_name)
    if problem:
        return problem
    removed = _describe(project, clip_ref, index)
    patched, snapshot_id, problem = _write(
        _ws, project_path, project,
        [RemoveEffect(track_index=track, clip_index=clip_index, effect_index=index)],
        f"before_effect_remove_{index}")
    if problem:
        return problem
    return _ok({"removed": removed, "stack_length": len(list_effects(patched, clip_ref)),
                "snapshot_id": snapshot_id})
