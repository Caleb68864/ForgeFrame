---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-ops.md"
sub_spec_number: 3
title: "MCP Tool Surface + Integration"
date: 2026-04-13
dependencies: [1, 2]
---

# Sub-Spec 3: MCP Tool Surface + Integration

Refined from `docs/specs/2026-04-13-stack-ops.md` — Stack-Ops feature.

## Scope

Register three new `@mcp.tool()` functions in `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

- `effects_copy(workspace_path, project_file, track, clip) -> dict`
- `effects_paste(workspace_path, project_file, track, clip, stack: str (JSON), mode: str = "append") -> dict`
- `effect_reorder(workspace_path, project_file, track, clip, from_index: int, to_index: int) -> dict`

These wrap Sub-Spec 2's pipeline (`stack_ops.serialize_stack` / `apply_paste` / `reorder_stack`) with workspace validation, snapshot creation, project parse/serialize, and `_ok` / `_err` envelope handling.

Add an integration test exercising the end-to-end copy → paste → re-parse round-trip against the existing fixture `tests/integration/fixtures/keyframe_project.kdenlive` (re-used from Spec 1 — no new fixtures required).

## Interface Contracts

### Provides
- MCP tool `effects_copy` — returns `{"status": "ok", "data": {"stack": {...}, "effect_count": int}}`.
- MCP tool `effects_paste` — returns `{"status": "ok", "data": {"effects_pasted": int, "mode": str, "snapshot_id": str}}`.
- MCP tool `effect_reorder` — returns `{"status": "ok", "data": {"from_index": int, "to_index": int, "snapshot_id": str}}`.
- All three importable as Python callables: `from workshop_video_brain.edit_mcp.server.tools import effects_copy, effects_paste, effect_reorder`.
- Errors flow through `_err` (no exceptions escape the tool boundary).

### Requires
- From Sub-Spec 1: `patcher.insert_effect_xml`, `patcher.remove_effect`, `patcher.reorder_effects`.
- From Sub-Spec 2: `stack_ops.serialize_stack`, `stack_ops.deserialize_stack`, `stack_ops.apply_paste`, `stack_ops.reorder_stack`.
- From existing infrastructure: `_require_workspace`, `_ok`, `_err`, `create_snapshot` (returns object with `.snapshot_id`), `parse_project`, `serialize_project`, `mcp` decorator.
- Fixture: `tests/integration/fixtures/keyframe_project.kdenlive` (Spec 1, already in repo).

### Shared State
- Workspace filesystem (`projects/snapshots/` for snapshot dirs, `<project_file>` for written project XML).

## Implementation Steps

### Step 1: Write failing integration test
- **File:** `tests/integration/test_stack_ops_mcp_tools.py` (new)
- **Tests:**
  - `test_tools_importable` — `from workshop_video_brain.edit_mcp.server.tools import effects_copy, effects_paste, effect_reorder` works and all three are callables.
  - `test_effects_copy_returns_stack` — Set up workspace, copy `keyframe_project.kdenlive` into it, call `effects_copy(workspace, project_file, track=2, clip=0)`. Assert `status == "ok"`, `data.effect_count >= 1`, `data.stack.effects[0].kdenlive_id == "transform"`.
  - `test_copy_paste_round_trip_append` — `effects_copy` source clip → JSON-encode `data.stack` → `effects_paste(target_track, target_clip, stack=<json>, mode="append")` → re-parse project → `patcher.list_effects(target)` shows `original_count + source_count` filters.
  - `test_paste_replace_clears_target` — Pre-add a filter on the target clip via `effect_add`, then paste with `mode="replace"`. Re-parse: target has exactly the source filters, original target filter is gone.
  - `test_effect_reorder_out_of_range_returns_err` — `effect_reorder(track, clip, from_index=99, to_index=0)` returns `{"status": "error", "message": <str>}` whose message contains the current stack length.
  - `test_each_write_returns_snapshot_id` — `effects_paste` and `effect_reorder` responses each contain `snapshot_id`; the corresponding `projects/snapshots/<id>/` directory exists on disk.
  - `test_paste_rewrites_track_clip_attrs_in_xml` — copy from `(2,0)`, paste to `(3,1)`, re-parse `.kdenlive` file, locate the pasted filter, assert its raw XML has `track="3"` and `clip_index="1"`.
  - `test_keyframe_preservation_round_trip` — On a clip, run `effect_add` to add a `transform` filter, then `effect_keyframe_set_rect` to write keyframes on `rect`. Read source `rect` property string. Run `effects_copy` then `effects_paste` to a different clip. Re-parse the project, locate the pasted filter, read its `rect` property string. Assert byte-exact equality with the source.
  - `test_full_suite_smoke` — already covered by the suite-wide pytest run; document as `[MECHANICAL]` step 5 below.
- **Run:** `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v`
- **Expected:** FAIL.

### Step 2: Implement `effects_copy` tool
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify (append in the effects/keyframes section, near `effect_add` at line 3666 and after the keyframe tools)
- **Pattern:** Follow `effect_add` (tools.py:3666-3723) for workspace validation and parse/serialize, and the keyframe tools (tools.py:3870-3903) for snapshot-with-snapshot_id.
- **Algorithm:**
  1. `@mcp.tool()` decorator; signature `def effects_copy(workspace_path: str, project_file: str, track: int, clip: int) -> dict:`.
  2. Imports inside function (matches existing tool style): `parse_project`, `stack_ops.serialize_stack`.
  3. `_require_workspace(workspace_path)` → `_err(str(exc))` on failure.
  4. Validate `project_path.exists()` → `_err`.
  5. `project = parse_project(project_path)`.
  6. `try: stack = stack_ops.serialize_stack(project, (track, clip))` `except IndexError as exc: return _err(str(exc))`.
  7. Return `_ok({"project_file": project_file, "stack": stack, "effect_count": len(stack["effects"])})`.
  8. **No snapshot** (read-only operation).

### Step 3: Implement `effects_paste` tool
- **File:** tools.py
- **Action:** modify
- **Algorithm:**
  1. Signature `def effects_paste(workspace_path: str, project_file: str, track: int, clip: int, stack: str, mode: str = "append") -> dict:`.
  2. Validate workspace + project_path as above.
  3. Parse `stack` JSON: `try: stack_dict = json.loads(stack); except json.JSONDecodeError as exc: return _err(f"Invalid stack JSON (expected output of effects_copy): {exc}")`.
  4. `record = create_snapshot(ws_path, project_path, description=f"before_effects_paste_{mode}"); snapshot_id = record.snapshot_id`. Wrap in try/except → `_err`.
  5. `project = parse_project(project_path)`.
  6. `try: count = stack_ops.apply_paste(project, (track, clip), stack_dict, mode); except (ValueError, IndexError) as exc: return _err(str(exc))`.
  7. `serialize_project(project, project_path)`.
  8. Return `_ok({"project_file": project_file, "track": track, "clip": clip, "effects_pasted": count, "mode": mode, "snapshot_id": snapshot_id})`.

### Step 4: Implement `effect_reorder` tool
- **File:** tools.py
- **Action:** modify
- **Algorithm:**
  1. Signature `def effect_reorder(workspace_path: str, project_file: str, track: int, clip: int, from_index: int, to_index: int) -> dict:`.
  2. Validate workspace + project_path.
  3. `record = create_snapshot(...)` → `snapshot_id`.
  4. `project = parse_project(project_path)`.
  5. `try: stack_ops.reorder_stack(project, (track, clip), from_index, to_index)` `except IndexError as exc:` enrich with current stack length: `try: available = patcher.list_effects(project, (track, clip)); except Exception: available = []; return _err(f"{exc}. Current stack: {len(available)} filters: {available}")`.
  6. `serialize_project(project, project_path)`.
  7. Return `_ok({"project_file": project_file, "track": track, "clip": clip, "from_index": from_index, "to_index": to_index, "snapshot_id": snapshot_id})`.

### Step 5: Verify integration tests pass
- **Run:** `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v`
- **Expected:** PASS.

### Step 6: Full regression suite
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS — zero regressions in Spec 1 keyframes, Kdenlive serializer, or any other existing tool.

### Step 7: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_stack_ops_mcp_tools.py`
- **Message:** `feat: MCP tools effects_copy, effects_paste, effect_reorder`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `effects_copy`, `effects_paste`, `effect_reorder`.
- `[STRUCTURAL]` `effects_copy(workspace_path, project_file, track, clip) -> dict` returns `{"status","data":{"stack":{...},"effect_count":int}}`.
- `[STRUCTURAL]` `effects_paste(workspace_path, project_file, track, clip, stack: str (JSON), mode: str = "append") -> dict` returns `{"status","data":{"effects_pasted":int,"mode":str,"snapshot_id":str}}`.
- `[STRUCTURAL]` `effect_reorder(workspace_path, project_file, track, clip, from_index: int, to_index: int) -> dict` returns `{"status","data":{"from_index":int,"to_index":int,"snapshot_id":str}}`.
- `[INTEGRATION]` All three tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` Against `tests/integration/fixtures/keyframe_project.kdenlive`, `effects_copy(track=2, clip=0)` returns `effect_count >= 1`, first filter `kdenlive_id == "transform"`.
- `[BEHAVIORAL]` End-to-end copy → JSON-encode → paste → `list_effects` shows correct count.
- `[BEHAVIORAL]` `mode="replace"` clears target's pre-existing filters.
- `[BEHAVIORAL]` `effect_reorder` with out-of-range `from_index` returns error envelope naming current stack length.
- `[BEHAVIORAL]` Each write call returns a `snapshot_id`; snapshot dir exists on disk.
- `[BEHAVIORAL]` Paste rewrites `track=`/`clip_index=` in the on-disk `.kdenlive` XML.
- `[INTEGRATION]` Keyframe preservation: pasted `rect` matches source byte-for-byte after re-parse.
- `[MECHANICAL]` `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

## Completeness Checklist

`effects_copy` response (`data`):

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `project_file` | `str` | required | echo |
| `stack` | `dict` (Sub-Spec 2 shape) | required | passed back to `effects_paste` |
| `effect_count` | `int` | required | LLM convenience |

`effects_paste` response (`data`):

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `project_file` | `str` | required | echo |
| `track` | `int` | required | echo |
| `clip` | `int` | required | echo |
| `effects_pasted` | `int` | required | caller verification |
| `mode` | `str` | required | echo |
| `snapshot_id` | `str` | required | restore via `snapshot_restore` |

`effect_reorder` response (`data`):

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `project_file` | `str` | required | echo |
| `track` | `int` | required | echo |
| `clip` | `int` | required | echo |
| `from_index` | `int` | required | echo |
| `to_index` | `int` | required | echo |
| `snapshot_id` | `str` | required | restore |

Edge-case envelopes (all return `{"status":"error","message": <str>}`):
- malformed `stack` JSON → message references `effects_copy`
- missing `effects` key → message references `effects_copy` (from `deserialize_stack`)
- invalid `mode` → message lists `append, prepend, replace`
- out-of-range `from_index` / `to_index` / `track` / `clip` → message names current stack length / playlist count
- missing project file → message names path
- missing workspace → message from `_require_workspace`

Snapshot policy:
- `effects_copy`: NO snapshot (read-only)
- `effects_paste`: snapshot before write
- `effect_reorder`: snapshot before write

## Verification Commands

- **Build:** `uv sync`
- **Tests (sub-spec):** `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v`
- **Tests (full suite, Constraint Must):** `uv run pytest tests/ -v`
- **Manual smoke (master spec verification step 3):**
  1. Open the resulting `.kdenlive` after copy + paste (append) in Kdenlive 25.x.
  2. Confirm both clips show their expected filter counts.
  3. Confirm the animated `transform` filter still animates on the paste target.
  4. Re-save in Kdenlive, re-open — no corruption.
- **Manual smoke (reorder):** `effect_reorder` middle → top, open in Kdenlive, confirm stack order in the Effect Stack panel.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:3666-3723` (`effect_add`) — workspace + project_path validation, parse → mutate → serialize, `_ok`/`_err` envelopes.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:3870-3903` (keyframe tool tail) — `create_snapshot` + `record.snapshot_id` capture and inclusion in response.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:22-26` — `_ok` / `_err` envelope helpers.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:1640-1670` (`snapshot_restore`) — confirms `snapshot_id` is the snapshot directory name under `projects/snapshots/`, used by the integration test to assert dir existence.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Add three `@mcp.tool()` functions wrapping the stack-ops pipeline. |
| `tests/integration/test_stack_ops_mcp_tools.py` | Create | End-to-end MCP tool tests using the existing `keyframe_project.kdenlive` fixture. |
