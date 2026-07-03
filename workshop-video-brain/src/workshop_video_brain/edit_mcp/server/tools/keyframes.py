"""Effect keyframe tools.

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
)





# ---------------------------------------------------------------------------
# Keyframe tools
# ---------------------------------------------------------------------------
def _keyframes_from_json(raw: str) -> list:
    """Parse the JSON-encoded keyframes payload to a list of Keyframe objects."""
    from workshop_video_brain.edit_mcp.pipelines.keyframes import (
        Keyframe,
        normalize_time,
    )

    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("keyframes must be a JSON array")
    # Validate each entry has a time key; the actual frame int is computed below
    # via the caller (which knows fps). Return list of raw dicts so the caller
    # can map to Keyframe after normalizing time -> frame.
    return data


def _build_keyframe_objects(items: list, fps: float) -> list:
    """Turn JSON keyframe dicts into Keyframe objects, normalizing time to frame."""
    from workshop_video_brain.edit_mcp.pipelines.keyframes import Keyframe

    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"keyframes[{i}] must be an object; got {type(item).__name__}")
        if "value" not in item:
            raise ValueError(f"keyframes[{i}] missing 'value'")
        easing = item.get("easing", "linear")
        # Derive integer frame from whichever time key is present.
        if "frame" in item:
            frame = int(item["frame"])
        elif "seconds" in item:
            frame = round(float(item["seconds"]) * float(fps))
        elif "timestamp" in item:
            ts = item["timestamp"]
            h, m, rest = ts.split(":")
            s, ms = rest.split(".")
            seconds = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
            frame = round(seconds * float(fps))
        else:
            raise ValueError(
                f"keyframes[{i}] must have one of 'frame', 'seconds', 'timestamp'"
            )
        out.append(Keyframe(frame=frame, value=item["value"], easing=easing))
    return out


def _keyframe_tool_impl(
    kind: str,
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
    property: str,
    keyframes: str,
    mode: str,
) -> dict:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.pipelines.keyframes import (
        build_keyframe_string,
        parse_keyframe_string,
        merge_keyframes,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    if mode not in ("replace", "merge"):
        return _err(f"mode must be 'replace' or 'merge'; got {mode!r}")

    try:
        items = _keyframes_from_json(keyframes)
    except json.JSONDecodeError as exc:
        return _err(f"Invalid keyframes JSON: {exc}")
    except ValueError as exc:
        return from_exception(exc)

    project = parse_project(project_path)
    fps = project.profile.fps

    try:
        new_kfs = _build_keyframe_objects(items, fps)
    except (ValueError, TypeError) as exc:
        return from_exception(exc)

    clip_ref = (track, clip)
    ease_family = workspace.keyframe_defaults.ease_family

    try:
        if mode == "merge":
            existing_str = patcher.get_effect_property(
                project, clip_ref, effect_index, property
            ) or ""
            if existing_str.strip():
                try:
                    existing_kfs = parse_keyframe_string(kind, existing_str, fps=fps)
                except ValueError:
                    # Not a keyframe string; fall back to replace semantics
                    existing_kfs = []
                combined = merge_keyframes(existing_kfs, new_kfs)
            else:
                combined = new_kfs
        else:
            combined = new_kfs

        out_str = build_keyframe_string(kind, combined, fps, ease_family)
    except IndexError as exc:
        try:
            available = patcher.list_effects(project, clip_ref)
        except Exception:
            available = []
        return _err(
            f"Invalid effect_index {effect_index}: {exc}. "
            f"Available effects: {available}"
        )
    except (ValueError, LookupError) as exc:
        return from_exception(exc)

    # Snapshot before write
    try:
        record = create_snapshot(
            ws_path, project_path, description=f"before_keyframe_{property}"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:
        return _err(f"Snapshot failed: {exc}")

    try:
        patcher.set_effect_property(project, clip_ref, effect_index, property, out_str)
    except IndexError as exc:
        try:
            available = patcher.list_effects(project, clip_ref)
        except Exception:
            available = []
        return _err(
            f"Invalid effect_index {effect_index}: {exc}. "
            f"Available effects: {available}"
        )
    except (ValueError, LookupError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)

    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "effect_index": effect_index,
        "property": property,
        "keyframes_written": out_str,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_find(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    name: str,
) -> dict:
    """Resolve the effect_index of a filter on a clip by name.

    Matches by kdenlive_id first, then mlt_service. Returns the stack index.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.pipelines import effect_find as effect_find_pipe

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    project = parse_project(project_path)
    try:
        idx = effect_find_pipe.find(project, (track, clip), name)
    except LookupError as exc:
        return from_exception(exc)
    except ValueError as exc:
        return from_exception(exc)
    except IndexError as exc:
        return from_exception(exc)

    return _ok({"effect_index": int(idx)})


@mcp.tool()
@tool_guard
def effect_keyframe_set_scalar(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
    property: str,
    keyframes: str,
    mode: str = "replace",
) -> dict:
    """Write a scalar keyframe animation string to an effect property."""
    return _keyframe_tool_impl(
        "scalar", workspace_path, project_file, track, clip,
        effect_index, property, keyframes, mode,
    )


@mcp.tool()
@tool_guard
def effect_keyframe_set_rect(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
    property: str,
    keyframes: str,
    mode: str = "replace",
) -> dict:
    """Write a rect keyframe animation string (x y w h [opacity]) to an effect property."""
    return _keyframe_tool_impl(
        "rect", workspace_path, project_file, track, clip,
        effect_index, property, keyframes, mode,
    )


@mcp.tool()
@tool_guard
def effect_keyframe_set_color(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_index: int,
    property: str,
    keyframes: str,
    mode: str = "replace",
) -> dict:
    """Write a color keyframe animation string (0xRRGGBBAA) to an effect property."""
    return _keyframe_tool_impl(
        "color", workspace_path, project_file, track, clip,
        effect_index, property, keyframes, mode,
    )
