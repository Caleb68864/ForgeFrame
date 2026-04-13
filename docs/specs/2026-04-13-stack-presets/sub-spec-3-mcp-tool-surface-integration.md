---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-presets.md"
sub_spec_number: 3
title: "MCP Tool Surface + Integration"
date: 2026-04-13
dependencies: [1, 2]
---

# Sub-Spec 3: MCP Tool Surface + Integration

Refined from `docs/specs/2026-04-13-stack-presets.md` — Stack Presets feature.

## Scope

Register four `@mcp.tool()` functions in `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

- `effect_stack_preset(workspace_path, project_file, track, clip, name, description="", tags="", apply_hints="") -> dict`
- `effect_stack_apply(workspace_path, project_file, track, clip, name, mode="") -> dict`
- `effect_stack_promote(workspace_path, name) -> dict`
- `effect_stack_list(workspace_path, scope="all") -> dict`

Each tool follows the existing `_require_workspace`/`_ok`/`_err` envelope convention, parses/serializes Kdenlive projects via existing adapters, and creates a snapshot via `workspace.create_snapshot` ONLY when the project is mutated (i.e. only `effect_stack_apply`).

`tags` and `apply_hints` are JSON-encoded strings (matching the existing `keyframes` MCP convention in this same file). `mode=""` means "use preset's `apply_hints.stack_order`".

Vault root resolution uses `pipelines.stack_presets.resolve_vault_root(repo_forge_project_json, ~/.claude/forge.json)`. The `repo_forge_project_json` path is resolved via `Path(__file__).resolve().parents[4] / "forge-project.json"` (or imported helper if one exists — verify during implementation).

Add an integration test file exercising end-to-end behaviors against the existing `tests/integration/fixtures/keyframe_project.kdenlive` fixture (re-used from Specs 1-2 — no new fixtures).

## Interface Contracts

### Provides
- MCP tool `effect_stack_preset` — returns `{"status":"ok","data":{"path":str,"effect_count":int,"scope":"workspace"}}`.
- MCP tool `effect_stack_apply` — returns `{"status":"ok","data":{"effects_applied":int,"mode":str,"snapshot_id":str,"blend_mode_hint":str|None,"track_placement_hint":str|None,"required_producers_hint":[...]}}`.
- MCP tool `effect_stack_promote` — returns `{"status":"ok","data":{"workspace_path":str,"vault_path":str}}`.
- MCP tool `effect_stack_list` — returns `{"status":"ok","data":{"presets":[...],"skipped":[...]}}`.
- All four importable as Python callables: `from workshop_video_brain.edit_mcp.server.tools import effect_stack_preset, effect_stack_apply, effect_stack_promote, effect_stack_list`.

### Requires
- From Sub-Spec 1: `Preset`, `ApplyHints`, `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root`.
- From Sub-Spec 2: `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`.
- From existing infra: `_require_workspace`, `_ok`, `_err`, `mcp` decorator, `parse_project`, `serialize_project`, `workspace.create_snapshot`, `workspace.read_manifest` (for `vault_note_path`).

### Shared State
- Workspace filesystem: `<ws>/stacks/`, `<ws>/projects/snapshots/`, `<ws>/<project_file>`.
- Vault filesystem: `<vault>/patterns/effect-stacks/`.
- Read-only: `<repo>/forge-project.json`, `~/.claude/forge.json`.

## Implementation Steps

### Step 1: Write failing integration tests
- **File:** `tests/integration/test_stack_presets_mcp_tools.py` (new)
- **Tests:**
  - `test_tools_importable` — `from workshop_video_brain.edit_mcp.server.tools import effect_stack_preset, effect_stack_apply, effect_stack_promote, effect_stack_list` works; all callable.
  - `test_preset_writes_yaml_and_returns_path` — Set up workspace; copy `keyframe_project.kdenlive` into it. Call `effect_stack_preset(workspace_path=ws, project_file="project.kdenlive", track=2, clip=0, name="test-preset")`. Assert `status=="ok"`, `data.scope=="workspace"`, file at `ws/stacks/test-preset.yaml` exists; YAML loads back into a `Preset` with `effect_count >= 1`.
  - `test_preset_unknown_service_returns_err` — Synthetically craft a clip whose filter has `mlt_service="nonexistent.service"` (modify the fixture project XML in tmp). Call `effect_stack_preset(...)`. Assert `status=="error"`; `message` contains `"nonexistent.service"`.
  - `test_preset_with_tags_and_apply_hints_json` — `effect_stack_preset(..., tags='["a","b"]', apply_hints='{"blend_mode":"screen","stack_order":"prepend"}')`. Reload YAML; assert `preset.tags == ("a","b")`, `preset.apply_hints.blend_mode == "screen"`, `preset.apply_hints.stack_order == "prepend"`.
  - `test_preset_invalid_tags_json_returns_err` — `tags="not-json"` returns `_err` mentioning JSON.
  - `test_apply_round_trip_filter_count` — Run `effect_stack_preset` on (track=2, clip=0). Then `effect_stack_apply(..., track=3, clip=1, name="test-preset")`. Re-parse project from disk. Use `patcher.list_effects` on (3,1); assert count grew by the source effect count.
  - `test_apply_mode_override_replace` — Pre-add a filter on the target clip via `effect_add` MCP tool. `effect_stack_apply(..., mode="replace")`. Re-parse: target has exactly the source filter count (existing filter dropped).
  - `test_apply_default_mode_uses_preset_hints` — Save preset with `apply_hints={"stack_order":"prepend"}`. `effect_stack_apply(..., mode="")`. Response `data.mode == "prepend"`.
  - `test_apply_missing_preset_returns_err_with_paths` — `effect_stack_apply(..., name="nonexistent")`. Returns `_err`; message contains both the workspace and vault search paths (or notes vault not configured).
  - `test_apply_returns_snapshot_id_and_dir_exists` — `effect_stack_apply` response has `data.snapshot_id`. Directory `ws/projects/snapshots/<id>/` exists.
  - `test_apply_response_includes_hint_fields` — Save preset with `apply_hints={"blend_mode":"screen","track_placement":"V2","required_producers":["audio"]}`. `effect_stack_apply` response contains `blend_mode_hint=="screen"`, `track_placement_hint=="V2"`, `required_producers_hint==["audio"]`.
  - `test_apply_keyframe_byte_exact` — Use `effect_keyframe_set_rect` to write keyframes on a source clip's `transform` filter `rect` property. `effect_stack_preset` it, then `effect_stack_apply` to a different clip. Re-parse project, read target filter's `rect` via `patcher.get_effect_property`. Assert byte-identical to source.
  - `test_promote_writes_vault_md_when_vault_configured` — Patch `resolve_vault_root` (or set up tmp `forge-project.json`) so vault resolves to a tmp dir. `effect_stack_preset` then `effect_stack_promote(workspace_path=ws, name="test-preset")`. Returns `_ok`; file at `<vault>/patterns/effect-stacks/test-preset.md` exists.
  - `test_promote_no_vault_returns_err` — Ensure neither `forge-project.json.vault_root` nor `~/.claude/forge.json.personal_vault` is set (or monkeypatch `resolve_vault_root` to return `None`). `effect_stack_promote` returns `_err` whose message contains `"Vault root not configured"` and mentions both `vault_root` and `personal_vault` config keys.
  - `test_promote_embeds_wikilink_from_manifest` — Set `workspace.yaml`'s `vault_note_path` to `"Videos/My Vid.md"`. Promote. Read produced `.md`. Body contains `[[My Vid]]`.
  - `test_promote_no_snapshot` — Promote does NOT create a `projects/snapshots/<id>` directory (preset-only operation, no project mutation).
  - `test_preset_no_snapshot` — `effect_stack_preset` does NOT create a snapshot directory.
  - `test_list_all_returns_both_tiers` — Save 2 workspace presets (via tool calls); place 1 hand-crafted vault preset. Call `effect_stack_list(workspace_path=ws, scope="all")`. Assert `len(data.presets) == 3`; scope labels are correct.
  - `test_list_workspace_only` — Same setup; `scope="workspace"` returns only the 2 workspace presets.
  - `test_full_suite_smoke` — covered by Step 4 mechanical run.
- **Run:** `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v`
- **Expected:** FAIL.

### Step 2: Implement the four MCP tools
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extend; append at end before any existing trailing block)
- **Pattern:** Follow `effect_keyframe_set_rect` (around line 3870) for parse → snapshot → mutate → serialize → `_ok` flow. Follow `effects_copy`/`effects_paste` from `tests/integration/test_stack_ops_mcp_tools.py` for stack-shape fluency. Use `_require_workspace`, `_ok`, `_err` exactly as elsewhere.
- **Imports inside tool functions** (lazy, matching the file's pattern):
  ```python
  from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
  from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
  from workshop_video_brain.edit_mcp.pipelines import stack_presets
  from workshop_video_brain.workspace import create_snapshot
  from workshop_video_brain.workspace.manifest import read_manifest
  import json
  ```
- **`effect_stack_preset`:**
  - `_require_workspace(workspace_path)` → `(ws_path, workspace)`.
  - Resolve `project_path = ws_path / project_file`; check exists; else `_err`.
  - Parse `tags` and `apply_hints` from JSON strings (empty string → defaults). Wrap `JSONDecodeError` in `_err`.
  - `project = parse_project(project_path)`.
  - Try: `preset = stack_presets.serialize_clip_to_preset(project, (track, clip), name=name, description=description, tags=tuple(tags_list), apply_hints=ApplyHints(**hints_dict) if hints_dict else None)`.
  - `stack_presets.validate_against_catalog(preset, strict=True)` — wrap `ValueError` in `_err`.
  - `path = stack_presets.save_preset(preset, workspace_root=ws_path, scope="workspace")`.
  - No snapshot (no project mutation).
  - Return `_ok({"path": str(path), "effect_count": len(preset.effects), "scope": "workspace"})`.
- **`effect_stack_apply`:**
  - `_require_workspace` and project-path checks as above.
  - Resolve vault root (best-effort, may be `None`): `vault_root = stack_presets.resolve_vault_root(_repo_forge_project_json_path(), Path.home()/".claude"/"forge.json")`.
  - `try: preset = stack_presets.load_preset(name, workspace_root=ws_path, vault_root=vault_root)` — wrap `FileNotFoundError` in `_err` (message already includes searched paths).
  - `mode_override = mode.strip() or None`. Validate it's in `{"append","prepend","replace"}` if non-empty, else `_err`.
  - `project = parse_project(project_path)`.
  - **Snapshot before write:** `record = create_snapshot(ws_path, project_path, description=f"before_stack_preset_{name}")`. `snapshot_id = record.snapshot_id`. Wrap exceptions in `_err`.
  - `result = stack_presets.apply_preset(project, (track, clip), preset, mode_override=mode_override)`.
  - `serialize_project(project, project_path)`.
  - Return `_ok({**result, "snapshot_id": snapshot_id, "required_producers_hint": list(result["required_producers_hint"])})` (cast tuple→list for JSON).
- **`effect_stack_promote`:**
  - `_require_workspace`.
  - `vault_root = stack_presets.resolve_vault_root(...)`. If `None`: `return _err("Vault root not configured -- set vault_root in forge-project.json or personal_vault in ~/.claude/forge.json")`.
  - Read manifest for `vault_note_path`: `manifest = read_manifest(ws_path)`. `note_path = Path(manifest.vault_note_path) if manifest.vault_note_path else None`.
  - `try: out_path = stack_presets.promote_to_vault(name, ws_path, vault_root, source_video_note_path=note_path)` — `FileNotFoundError` → `_err`.
  - Return `_ok({"workspace_path": str(ws_path / "stacks" / f"{name}.yaml"), "vault_path": str(out_path)})`.
- **`effect_stack_list`:**
  - `_require_workspace`.
  - `vault_root = stack_presets.resolve_vault_root(...)` (may be `None`; that's fine for scope="workspace").
  - If `scope` not in `{"workspace","vault","all"}`: `_err`.
  - `result = stack_presets.list_presets(ws_path, vault_root, scope=scope)`.
  - Return `_ok({"presets": result["presets"], "skipped": result["skipped"]})`.

- Add a small private helper `_repo_forge_project_json_path()` near the top of the new block:
  ```python
  def _repo_forge_project_json_path() -> Path:
      # Walk up from this file's location to find forge-project.json
      here = Path(__file__).resolve()
      for parent in here.parents:
          candidate = parent / "forge-project.json"
          if candidate.exists():
              return candidate
      return Path("forge-project.json")  # fallback (resolve_vault_root tolerates missing)
  ```

### Step 3: Verify integration tests pass
- **Run:** `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v`
- **Expected:** PASS.

### Step 4: Run full suite
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS — zero regressions on the baseline (2407+ tests).

### Step 5: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_stack_presets_mcp_tools.py`
- **Message:** `feat: mcp tools for effect stack presets (preset, apply, promote, list)`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote`, `effect_stack_list`.
- `[STRUCTURAL]` `effect_stack_preset` signature + return shape match spec.
- `[STRUCTURAL]` `effect_stack_apply` signature + return shape match spec; `mode=""` means use preset hint.
- `[STRUCTURAL]` `effect_stack_promote` signature + return shape match spec.
- `[STRUCTURAL]` `effect_stack_list` signature + return shape match spec.
- `[INTEGRATION]` All four tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` Fixture-driven preset save produces a valid YAML file with `effect_count >= 1`.
- `[BEHAVIORAL]` Preset save with unknown `mlt_service` returns `_err` naming the service.
- `[BEHAVIORAL]` End-to-end preset → apply → re-parse: target clip has correct count; keyframes byte-exact.
- `[BEHAVIORAL]` `mode="replace"` overrides preset hint.
- `[BEHAVIORAL]` Apply with missing name returns `_err` listing both searched paths.
- `[BEHAVIORAL]` Apply response includes hint fields verbatim.
- `[BEHAVIORAL]` Only apply creates a snapshot; preset/promote do not.
- `[BEHAVIORAL]` Promote embeds `[[stem]]` wikilink when manifest has `vault_note_path`.
- `[BEHAVIORAL]` Promote with no vault config returns `_err` with the exact message specified in the master spec.
- `[BEHAVIORAL]` `effect_stack_list(scope="all")` returns presets across both tiers with scope labels.
- `[MECHANICAL]` `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` passes (no regressions).

## Completeness Checklist

### `effect_stack_preset` parameters
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| workspace_path | str | required | `_require_workspace` |
| project_file | str | required | project file resolution |
| track | int | required | clip_ref |
| clip | int | required | clip_ref |
| name | str | required | preset filename |
| description | str (default "") | optional | metadata |
| tags | str JSON-encoded list (default "") | optional | metadata |
| apply_hints | str JSON-encoded dict (default "") | optional | apply behavior |

### `effect_stack_apply` parameters
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| workspace_path | str | required | `_require_workspace` |
| project_file | str | required | project file resolution |
| track | int | required | target clip_ref |
| clip | int | required | target clip_ref |
| name | str | required | preset name lookup |
| mode | str (default "") | optional | "" → use preset hint; else override |

### `effect_stack_promote` parameters
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| workspace_path | str | required | `_require_workspace` + manifest read |
| name | str | required | preset name lookup |

### `effect_stack_list` parameters
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| workspace_path | str | required | `_require_workspace` |
| scope | str (default "all") | optional | "workspace" / "vault" / "all" |

### Snapshot policy
- `effect_stack_preset`: NO snapshot (no project mutation).
- `effect_stack_apply`: snapshot REQUIRED (mutates project). `description=f"before_stack_preset_{name}"`.
- `effect_stack_promote`: NO snapshot (no project mutation).
- `effect_stack_list`: NO snapshot (read-only).

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v`
- **Full suite:** `uv run pytest tests/ -v` (must show zero regressions)
- **Manual:** Start the MCP server; verify the four tools appear in the tool list.
- **Acceptance:** Each acceptance criterion has a corresponding test in Step 1.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines ~3870-3970 (`effect_keyframe_set_rect`) — canonical parse → snapshot → mutate → serialize → `_ok` flow.
- Same file's existing top-level helpers `_require_workspace`, `_ok`, `_err` (lines ~22-55) — re-use, do not redefine.
- `tests/integration/test_stack_ops_mcp_tools.py` — fixture setup pattern (copy `keyframe_project.kdenlive` into a tmp workspace, then exercise tools).
- `workshop-video-brain/src/workshop_video_brain/workspace/manifest.py::read_manifest` — for `vault_note_path` lookup.
- JSON-encoded MCP params: `keyframes: str` parameter in `effect_keyframe_set_rect` is the precedent — emulate its `json.loads` + `_err` wrapping.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Append four `@mcp.tool()` registrations + helper |
| `tests/integration/test_stack_presets_mcp_tools.py` | Create | End-to-end MCP tool tests |
