"""Effect add/list/info, stack copy/paste/reorder, and stack presets.

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
    nonneg_index,
)
from workshop_video_brain.edit_mcp.server import tools as _tools_pkg
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
)



@mcp.tool()
@tool_guard
def effect_add(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_name: str,
    params: str = "",
) -> dict:
    """Add a named effect to a clip in a Kdenlive project.

    effect_name is any MLT service identifier (e.g. 'avfilter.eq',
    'lift_gamma_gain'). params is a JSON string of key-value pairs
    (e.g. '{"av.brightness": "0.1"}') or empty for effect defaults.
    Snapshot is created before modifying the project.
    """
    import json as _json
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    if not effect_name or not effect_name.strip():
        return invalid_input("effect_name must be a non-empty string", "Pass an MLT service id, e.g. 'avfilter.gblur' or 'lift_gamma_gain'.", param="effect_name")

    # Reject negative indexes up front: apply_effect indexes Python lists, so a
    # negative track/clip would silently wrap to the wrong element (false
    # success) rather than erroring.
    idx_err = nonneg_index("index", track=track, clip=clip)
    if idx_err is not None:
        return idx_err

    # Parse params JSON
    param_dict: dict[str, str] = {}
    if params.strip():
        try:
            param_dict = _json.loads(params)
        except _json.JSONDecodeError as exc:
            return err(f"Invalid params JSON: {exc}", error_type="bad_json_param", suggestion='Provide a valid JSON object, e.g. {"opacity": 0.5}.', cause=str(exc))
    if not isinstance(param_dict, dict):
        return invalid_input("params must decode to a JSON object", 'Provide a JSON object of name->value pairs, e.g. {"opacity": 0.5}.', param="params")

    # Parse + apply in memory BEFORE snapshotting: a corrupt project or a bad
    # track/clip index then fails cleanly without leaving a leaked snapshot of
    # the (unchanged) file behind. The snapshot is taken only once we are about
    # to actually write.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001
        return from_exception(exc)

    try:
        patched = apply_effect(project, track, clip, effect_name, param_dict)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    create_snapshot(ws_path, project_path, description=f"before_effect_{effect_name}")
    serialize_project(patched, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "effect_name": effect_name,
        "params": param_dict,
    })


@mcp.tool()
@tool_guard
def effect_list_common() -> dict:
    """List common Kdenlive/MLT effects with descriptions.

    This is an informational reference -- any effect name can be used
    with effect_add regardless of whether it appears in this list.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines import (
            effect_catalog as _catalog,
        )
    except ModuleNotFoundError:
        return _err(
            "Effect catalog not generated. Run: "
            "uv run workshop-video-brain catalog regenerate "
            "(or scripts/generate_effect_catalog.py)"
        )
    effects = []
    for eff in _catalog.CATALOG.values():
        desc = eff.description or ""
        short = desc if len(desc) <= 80 else desc[:80] + "..."
        effects.append({
            "kdenlive_id": eff.kdenlive_id,
            "mlt_service": eff.mlt_service,
            "display_name": eff.display_name,
            "category": eff.category,
            "short_description": short,
        })
    return _ok({"effects": effects})


def _effect_def_to_dict(eff) -> dict:
    return {
        "kdenlive_id": eff.kdenlive_id,
        "mlt_service": eff.mlt_service,
        "display_name": eff.display_name,
        "description": eff.description,
        "category": eff.category,
        "params": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "type": p.type.value,
                "default": p.default,
                "min": p.min,
                "max": p.max,
                "decimals": p.decimals,
                "values": list(p.values),
                "value_labels": list(p.value_labels),
                "keyframable": p.keyframable,
            }
            for p in eff.params
        ],
    }


@mcp.tool()
@tool_guard
def effect_info(name: str) -> dict:
    """Return full schema for a Kdenlive effect by kdenlive_id or MLT service tag.

    Looks up the catalog generated from /usr/share/kdenlive/effects/. Use
    `effect_list_common` to discover available effect ids.
    """
    if not name or not name.strip():
        return _err("Effect name cannot be empty.")
    try:
        from workshop_video_brain.edit_mcp.pipelines import (
            effect_catalog as _catalog,
        )
    except ModuleNotFoundError:
        return _err(
            "Effect catalog not generated. Run: "
            "uv run workshop-video-brain catalog regenerate "
            "(or scripts/generate_effect_catalog.py)"
        )
    eff = _catalog.find_by_name(name) or _catalog.find_by_service(name)
    if eff is None:
        return _err(
            f"Effect not found: {name}. Try `effect_list_common` for the registry."
        )
    return _ok(_effect_def_to_dict(eff))




# ---------------------------------------------------------------------------
# Stack-Ops tools (effects_copy / effects_paste / effect_reorder)
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def effects_copy(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
) -> dict:
    """Serialize a clip's filter stack to a JSON-friendly dict (read-only).

    Returns ``{"stack": {...}, "effect_count": int}``. The ``stack`` value is
    the output of ``stack_ops.serialize_stack`` and can be JSON-encoded and
    passed back to ``effects_paste``.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.pipelines import stack_ops

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    project = parse_project(project_path)
    try:
        stack = stack_ops.serialize_stack(project, (track, clip))
    except IndexError as exc:
        return from_exception(exc)

    return _ok({
        "project_file": project_file,
        "stack": stack,
        "effect_count": len(stack["effects"]),
    })


@mcp.tool()
@tool_guard
def effects_paste(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    stack: str,
    mode: str = "append",
) -> dict:
    """Paste a serialized filter stack onto a clip.

    ``stack`` is a JSON string (output of ``effects_copy`` ``data.stack``).
    ``mode`` is one of ``append``, ``prepend``, ``replace``. Snapshot is
    created before modifying the project.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import stack_ops
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    try:
        stack_dict = json.loads(stack)
    except json.JSONDecodeError as exc:
        return err(
            f"Invalid stack JSON (expected output of effects_copy): {exc}",
            error_type="bad_json_param",
            suggestion="Pass the JSON from effects_copy data.stack unchanged.",
            param="stack", cause=str(exc),
        )

    # Parse + apply in memory before snapshotting so a corrupt project or bad
    # index fails cleanly with no leaked snapshot.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001
        return from_exception(exc)
    try:
        count = stack_ops.apply_paste(project, (track, clip), stack_dict, mode)
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    try:
        record = create_snapshot(
            ws_path, project_path, description=f"before_effects_paste_{mode}"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:
        return operation_failed("Snapshot failed", cause=exc, suggestion="Check the workspace projects/snapshots directory is writable.")

    serialize_project(project, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "effects_pasted": count,
        "mode": mode,
        "snapshot_id": snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_reorder(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    from_index: int,
    to_index: int,
) -> dict:
    """Reorder a filter within a clip's filter stack.

    Snapshot is created before modifying the project. Returns an error envelope
    naming the current stack length when indices are out of range.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.pipelines import stack_ops
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    # Parse + validate indexes BEFORE snapshotting so a bad index never leaves a
    # leaked snapshot behind.
    try:
        project = parse_project(project_path)
        available = patcher.list_effects(project, (track, clip))
    except (ValueError, IndexError, KeyError) as exc:
        return from_exception(exc)
    except Exception as exc:  # noqa: BLE001
        return from_exception(exc)
    stack_len = len(available)
    for label, idx in (("from_index", from_index), ("to_index", to_index)):
        if idx < 0 or idx >= stack_len:
            # Preserve the legacy "Current stack" wording (tests substring-match)
            # and add the structured keys.
            return err(
                f"{label} {idx} out of range (clip has {stack_len} filters). "
                f"Current stack: {stack_len} filters: {available}",
                error_type="invalid_index",
                suggestion="Pass from_index/to_index within the filter stack; use effect_stack_list to see indices.",
                given=idx,
                valid_range=f"0-{stack_len - 1}" if stack_len else "none (clip has no filters)",
            )

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_effect_reorder"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:
        return operation_failed("Snapshot failed", cause=exc, suggestion="Check the workspace projects/snapshots directory is writable.")

    try:
        stack_ops.reorder_stack(project, (track, clip), from_index, to_index)
    except (IndexError, ValueError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "from_index": from_index,
        "to_index": to_index,
        "snapshot_id": snapshot_id,
    })




# ---------------------------------------------------------------------------
# Stack Presets (save / apply / promote / list)
# ---------------------------------------------------------------------------
def _repo_forge_project_json_path() -> Path:
    """Walk up from this file to find forge-project.json; fallback to CWD."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "forge-project.json"
        if candidate.exists():
            return candidate
    return Path("forge-project.json")


def _resolve_vault_root_for_tools():
    from workshop_video_brain.edit_mcp.pipelines import stack_presets
    return stack_presets.resolve_vault_root(
        _repo_forge_project_json_path(),
        Path.home() / ".claude" / "forge.json",
    )


@mcp.tool()
@tool_guard
def effect_stack_preset(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    name: str,
    description: str = "",
    tags: str = "",
    apply_hints: str = "",
) -> dict:
    """Serialize a clip's filter stack into a workspace-tier preset YAML.

    ``tags`` is a JSON-encoded list[str]; ``apply_hints`` is a JSON-encoded
    dict matching ``ApplyHints`` fields. Empty strings use defaults. No
    snapshot is taken (read-only on the project).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.pipelines import stack_presets

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    tags_list: list[str] = []
    if tags.strip():
        try:
            parsed = json.loads(tags)
        except json.JSONDecodeError as exc:
            return _err(f"Invalid tags JSON (expected list[str]): {exc}")
        if not isinstance(parsed, list) or not all(isinstance(t, str) for t in parsed):
            return _err("tags must be a JSON list of strings")
        tags_list = parsed

    hints_obj = None
    if apply_hints.strip():
        try:
            hints_dict = json.loads(apply_hints)
        except json.JSONDecodeError as exc:
            return _err(f"Invalid apply_hints JSON (expected dict): {exc}")
        if not isinstance(hints_dict, dict):
            return _err("apply_hints must be a JSON object")
        try:
            hints_obj = stack_presets.ApplyHints(**hints_dict)
        except Exception as exc:  # noqa: BLE001
            return _err(f"Invalid apply_hints: {exc}")

    project = parse_project(project_path)
    try:
        preset = stack_presets.serialize_clip_to_preset(
            project,
            (track, clip),
            name=name,
            description=description,
            tags=tuple(tags_list),
            created_by="effect_stack_preset",
            apply_hints=hints_obj,
        )
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    try:
        stack_presets.validate_against_catalog(preset, strict=True)
    except ValueError as exc:
        return from_exception(exc)

    try:
        path = stack_presets.save_preset(
            preset, workspace_root=ws_path, scope="workspace"
        )
    except Exception as exc:  # noqa: BLE001
        return _err(f"Failed to save preset: {exc}")

    return _ok({
        "path": str(path),
        "effect_count": len(preset.effects),
        "scope": "workspace",
        "name": preset.name,
    })


@mcp.tool()
@tool_guard
def effect_stack_apply(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    name: str,
    mode: str = "",
) -> dict:
    """Apply a saved preset stack to a clip. Snapshot is taken before write.

    ``mode`` is ``""`` (use preset's ``apply_hints.stack_order``) or one of
    ``append``/``prepend``/``replace``.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines import stack_presets
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type="missing_file", suggestion="Create a working copy with project_create_working_copy, or check the project path.", path=str(project_file))

    mode_override = mode.strip() or None
    if mode_override is not None and mode_override not in ("append", "prepend", "replace"):
        return _err(
            f"mode must be one of: append, prepend, replace; got {mode!r}"
        )

    vault_root = _tools_pkg._resolve_vault_root_for_tools()
    try:
        preset = stack_presets.load_preset(
            name, workspace_root=ws_path, vault_root=vault_root
        )
    except FileNotFoundError as exc:
        return from_exception(exc)

    try:
        record = create_snapshot(
            ws_path, project_path, description=f"before_apply_{name}"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return _err(f"Snapshot failed: {exc}")

    project = parse_project(project_path)
    try:
        result = stack_presets.apply_preset(
            project, (track, clip), preset, mode_override=mode_override
        )
    except (ValueError, IndexError) as exc:
        return from_exception(exc)

    serialize_project(project, project_path)

    return _ok({
        "effects_applied": result["effects_applied"],
        "mode": result["mode"],
        "blend_mode_hint": result["blend_mode_hint"],
        "track_placement_hint": result["track_placement_hint"],
        "required_producers_hint": list(result["required_producers_hint"]),
        "snapshot_id": snapshot_id,
        "project_file": project_file,
        "track": track,
        "clip": clip,
    })


@mcp.tool()
@tool_guard
def effect_stack_promote(workspace_path: str, name: str) -> dict:
    """Promote a workspace preset to the vault tier (markdown with frontmatter).

    Reads ``workspace.yaml``'s ``vault_note_path`` to embed a ``[[stem]]``
    wikilink when set. No snapshot (no project mutation).
    """
    from workshop_video_brain.edit_mcp.pipelines import stack_presets
    from workshop_video_brain.workspace.manifest import read_manifest

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    vault_root = _tools_pkg._resolve_vault_root_for_tools()
    if vault_root is None:
        return _err(
            "Vault root not configured -- set vault_root in forge-project.json "
            "or personal_vault in ~/.claude/forge.json"
        )

    try:
        manifest = read_manifest(ws_path)
        note_path_str = manifest.vault_note_path or ""
    except Exception:  # noqa: BLE001
        note_path_str = ""
    note_path = Path(note_path_str) if note_path_str else None

    try:
        out_path = stack_presets.promote_to_vault(
            name, ws_path, vault_root, source_video_note_path=note_path
        )
    except FileNotFoundError as exc:
        return from_exception(exc)
    except Exception as exc:  # noqa: BLE001
        return _err(f"Failed to promote preset: {exc}")

    return _ok({
        "workspace_path": str(ws_path / "stacks" / f"{name}.yaml"),
        "vault_path": str(out_path),
        "name": name,
    })


@mcp.tool()
@tool_guard
def effect_stack_list(workspace_path: str, scope: str = "all") -> dict:
    """List presets across workspace and/or vault tiers.

    ``scope`` is one of ``workspace``, ``vault``, ``all``.
    """
    from workshop_video_brain.edit_mcp.pipelines import stack_presets

    if scope not in ("workspace", "vault", "all"):
        return _err(
            f"scope must be one of: workspace, vault, all; got {scope!r}"
        )

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)

    vault_root = _tools_pkg._resolve_vault_root_for_tools()
    result = stack_presets.list_presets(ws_path, vault_root, scope=scope)
    return _ok({
        "presets": result["presets"],
        "skipped": result["skipped"],
    })
