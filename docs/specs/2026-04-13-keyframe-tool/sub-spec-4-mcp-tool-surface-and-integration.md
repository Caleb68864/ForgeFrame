---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-keyframe-tool.md"
sub_spec_number: 4
title: "MCP Tool Surface + Integration"
date: 2026-04-13
dependencies: [1, 2, 3]
---

# Sub-Spec 4: MCP Tool Surface + Integration

Refined from spec.md — ForgeFrame keyframe tool.

## Scope

Register four new `@mcp.tool()` functions in
`workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

- `effect_keyframe_set_scalar`
- `effect_keyframe_set_rect`
- `effect_keyframe_set_color`
- `effect_find`

Each keyframe tool:
1. Loads and validates workspace via the existing `_require_workspace` helper.
2. Resolves the project file path and parses it via `parse_project`.
3. Reads the project's `fps` from `project.profile.fps` **per call** (no caching — master-spec Must-Not).
4. Calls `keyframes.normalize_time` / `keyframes.build_keyframe_string` (Sub-Spec 2) using `workspace.keyframe_defaults.ease_family` (Sub-Spec 3).
5. If `mode == "merge"`: reads existing property via `patcher.get_effect_property` (Sub-Spec 1), parses via `keyframes.parse_keyframe_string`, merges via `keyframes.merge_keyframes`, re-builds the animation string.
6. Writes via `patcher.set_effect_property` (Sub-Spec 1).
7. Creates a snapshot BEFORE the write via `workshop_video_brain.workspace.snapshot.create(workspace_root, project_file_path, description)`. **Note:** the existing `effect_add` at `tools.py:3708` calls `WorkspaceManager.create_snapshot(...)` which does NOT exist — that code path is a latent bug. Do not copy it. Use the real API directly: `from workshop_video_brain.workspace import create_snapshot`. The function returns a `SnapshotRecord`; the snapshot directory name (the id `restore()` expects) is NOT currently exposed on the record. See Step 4 below for the required API fix.
8. Serializes via `serialize_project`.
9. Returns `{"status":"success","data":{...,"snapshot_id":"..."}}` including the snapshot identifier.

`effect_find` tool is thin — validates workspace, parses project, calls `effect_find.find`, returns `{"status":"success","data":{"effect_index":<int>}}`.

## Interface Contracts

### Provides
Four MCP tools registered on the global `mcp` FastMCP instance. All follow the established `{"status","data"|"message"}` response envelope (see `_ok` / `_err` helpers at `tools.py:22-27`).

### Requires
- Sub-Spec 1: `patcher.get_effect_property`, `patcher.set_effect_property`, `patcher.list_effects` (used in error messages).
- Sub-Spec 2: `pipelines.keyframes.{normalize_time, build_keyframe_string, parse_keyframe_string, merge_keyframes, Keyframe}`.
- Sub-Spec 3: `pipelines.effect_find.find`, and `workspace.keyframe_defaults.ease_family` available on the opened `Workspace`.

### Shared State
- Snapshot mechanism at `workshop_video_brain.workspace.snapshot.create` (re-exported as `workspace.create_snapshot`) and the `.kdenlive` project file on disk.
- The global `mcp` FastMCP instance (imported `from workshop_video_brain.server import mcp` — see `tools.py:15`).

### Pre-Flight API Fix (REQUIRED before implementing tools)

The snapshot API currently has two defects this sub-spec MUST fix:

1. **`WorkspaceManager.create_snapshot` does not exist** yet four existing call
   sites in `tools.py` reference it (lines 3578, 3708, 3942, 3980 — for
   `effect_add`, etc). Those paths raise `AttributeError` when exercised. Fix:
   update all existing call sites AND new call sites to use
   `from workshop_video_brain.workspace import create_snapshot` directly.
2. **Snapshot directory name is not returned.** `snapshot.create()` builds
   `snap_name = f"{ts}-{slug}"` internally (with collision suffix) but does not
   expose it on `SnapshotRecord`. The new keyframe tools need this as
   `snapshot_id` (matching the format `snapshot_restore` accepts). Fix: add
   `snapshot_id: str = ""` field to `SnapshotRecord` in
   `workshop-video-brain/src/workshop_video_brain/core/models/project.py`, and
   set `record.snapshot_id = snap_name` inside `snapshot.create` before
   returning. Update `tests/unit/test_snapshot*.py` if any exist.

Both fixes are in-scope for this sub-spec — the keyframe tools literally
cannot satisfy the `data.snapshot_id` acceptance criterion otherwise.

## Implementation Steps

### Step 1: Create test fixture project
- **File:** `tests/integration/fixtures/keyframe_project.kdenlive`
- **Action:** create
- **Content:** A minimal `.kdenlive` MLT XML with:
  - `<profile>` declaring 30 fps, 1920x1080.
  - One video producer.
  - Two tracks (one video, one audio), giving `playlists[2]` for the video track.
  - One clip entry on the video track.
  - A pre-existing `<filter mlt_service="affine" track="2" clip_index="0"><property name="kdenlive_id">transform</property><property name="rect">0 0 1920 1080 1</property></filter>` inserted at a `position_hint="after_tractor"` slot.
- **Pattern:** copy-adapt an existing small fixture if present (search `tests/integration/fixtures/` for `.kdenlive` files). If none exist, hand-write using an existing `smoke-test` project as a structural reference.

### Step 2: Write failing integration tests
- **File:** `tests/integration/test_keyframe_mcp_tools.py`
- **Tests:**
  - `test_four_tools_are_registered_on_mcp`
  - `test_effect_find_returns_index_for_transform`
  - `test_effect_keyframe_set_rect_writes_animation_string_and_roundtrips`
  - `test_effect_keyframe_set_scalar_basic`
  - `test_effect_keyframe_set_color_basic`
  - `test_mode_merge_preserves_non_overlapping_frames`
  - `test_mode_merge_overwrites_same_frame`
  - `test_invalid_effect_index_error_lists_available_effects`
  - `test_each_call_produces_snapshot_id_in_response`
  - `test_fps_read_per_call_not_cached` — mutate `project.profile.fps` between two calls and assert the second call emits timestamps at the new fps.
  - `test_ease_family_workspace_config_flows_through` — set `workspace.keyframe_defaults.ease_family = "expo"` on the workspace manifest, call `effect_keyframe_set_scalar` with `easing="ease_in"`, assert the written keyframe string contains operator `p` (expo_in) and NOT operator `g` (cubic_in). This guards against a worker hard-coding `"cubic"` in tools.py.
  - `test_color_keyframe_emits_mlt_hex_format` — call `effect_keyframe_set_color` with `value="#ff0000"` and assert the written string contains `0xff0000ff` (opaque alpha appended).
- **Fixture copy:** each test `shutil.copy` the fixture into a `tmp_path` workspace so writes do not mutate the committed fixture.
- **Run:** `uv run pytest tests/integration/test_keyframe_mcp_tools.py -v`
- **Expected:** all fail.

### Step 3: Implement `effect_find` MCP tool
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Location:** append immediately after `effect_list_common` (line ~3735) to keep effect-family tools grouped.
- **Pattern:** mirror `effect_add` signature/structure at `tools.py:3666`.
- **Signature:**
  ```python
  @mcp.tool()
  def effect_find(
      workspace_path: str,
      project_file: str,
      track: int,
      clip: int,
      name: str,
  ) -> dict:
  ```
- **Body:**
  - `_require_workspace` → `parse_project` → `pipelines.effect_find.find(project, (track, clip), name)` → `_ok({"effect_index": i})`.
  - Catch `LookupError` and `ValueError` separately, return via `_err(str(exc))`.

### Step 4: Implement `effect_keyframe_set_scalar`
- **Signature:**
  ```python
  @mcp.tool()
  def effect_keyframe_set_scalar(
      workspace_path: str,
      project_file: str,
      track: int,
      clip: int,
      effect_index: int,
      property: str,
      keyframes: str,   # JSON-encoded list[{time_union, value, easing}]
      mode: str = "replace",  # Literal["replace","merge"] validated in body
  ) -> dict:
  ```
- **Body outline:**
  1. `_require_workspace`, parse `keyframes` JSON, validate `mode in {"replace","merge"}`.
  2. Parse project; `fps = project.profile.fps`.
  3. Convert JSON list into `Keyframe` objects (each item: expect one of `frame`/`seconds`/`timestamp` + `value` + `easing`).
  4. If `mode == "merge"`: `existing_str = patcher.get_effect_property(project, (track, clip), effect_index, property) or ""`; if present parse with `parse_keyframe_string("scalar", existing_str)`; merge; else skip merge.
  5. `out_str = build_keyframe_string("scalar", combined, fps, workspace.keyframe_defaults.ease_family)`.
  6. Snapshot: `from workshop_video_brain.workspace import create_snapshot` then `record = create_snapshot(ws_path, project_path, description=f"before_keyframe_{property}"); snapshot_id = record.snapshot_id` (uses the new field added by the pre-flight API fix).
  7. `patcher.set_effect_property(project, (track, clip), effect_index, property, out_str)`.
  8. `serialize_project(project, project_path)`.
  9. Return `_ok({"project_file":..., "track":..., "clip":..., "effect_index":..., "property":..., "keyframes_written": out_str, "snapshot_id": snapshot_id})`.
- **Error paths:** wrap in try/except for `(IndexError, LookupError, ValueError, json.JSONDecodeError)`; on `IndexError` from bad `effect_index`, include `patcher.list_effects(project, (track, clip))` in the error payload.

### Step 5: Implement `effect_keyframe_set_rect`
- Same as scalar but `kind="rect"` and accepts `value` as 4-tuple or 5-tuple.

### Step 6: Implement `effect_keyframe_set_color`
- Same as scalar but `kind="color"`.

### Step 7: Ensure imports registered
- `tools.py` is imported by `server.py` on startup (see module docstring lines 7-8). No change needed to `server.py`; the new `@mcp.tool()` decorators auto-register when `tools.py` is imported.

### Step 8: Run integration tests
- **Run:** `uv run pytest tests/integration/test_keyframe_mcp_tools.py -v`
- **Expected:** PASS.

### Step 9: Full-suite regression
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS; no regressions in `test_mcp_tools.py` or elsewhere.

### Step 10: MCP registration check (evidence for `[INTEGRATION]` criterion)

Registration via `@mcp.tool()` decorator is a side effect of module import. The reliable, version-agnostic check is that each function imports as a callable:

```python
from workshop_video_brain.edit_mcp.server import tools

for name in ("effect_keyframe_set_scalar",
             "effect_keyframe_set_rect",
             "effect_keyframe_set_color",
             "effect_find"):
    assert callable(getattr(tools, name)), f"{name} missing from tools module"
```

Include this block in `test_four_tools_are_registered_on_mcp`. Do NOT assert against FastMCP internals (`mcp._tools`, `mcp._tool_manager`, etc.) — those APIs differ across FastMCP versions. If the existing test suite (`tests/integration/test_mcp_tools.py`) already has a reusable registration-assertion helper, prefer that pattern verbatim.

### Step 11: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_keyframe_mcp_tools.py tests/integration/fixtures/keyframe_project.kdenlive`
- **Message:** `feat: mcp tool surface for keyframes and effect-find`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`, `effect_find`.
- `[STRUCTURAL]` Each keyframe tool matches the signature in master-spec criterion (returns dict with `snapshot_id`).
- `[STRUCTURAL]` `effect_find` signature as in master spec.
- `[INTEGRATION]` Starting MCP server exposes all four tools.
- `[BEHAVIORAL]` Rect tool against fixture writes expected keyframe string; re-parsing yields same keyframe list.
- `[BEHAVIORAL]` `mode="merge"` preserves non-overlapping frames and overwrites same-frame entries.
- `[BEHAVIORAL]` `effect_find(workspace, track=2, clip=0, name="transform")` returns `0`.
- `[BEHAVIORAL]` Invalid `effect_index` raises MCP-layer error containing list of available effects.
- `[BEHAVIORAL]` Each call returns a snapshot id.
- `[MECHANICAL]` `uv run pytest tests/integration/test_keyframe_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.
- `[INTEGRATION]` Workspace `keyframe_defaults.ease_family = "expo"` flows through: calling `effect_keyframe_set_scalar` with `easing="ease_in"` writes operator `p` (expo_in) not `g` (cubic_in).
- `[BEHAVIORAL]` Color tool emits MLT `0xRRGGBBAA` canonical format; `value="#ff0000"` produces `0xff0000ff` in the written string.

## Completeness Checklist

### Tool input parameters (per keyframe tool)

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `workspace_path` | `str` | required | `_require_workspace` |
| `project_file` | `str` | required | resolves project path under workspace root |
| `track` | `int` | required | `patcher` `clip_ref` tuple |
| `clip` | `int` | required | `patcher` `clip_ref` tuple |
| `effect_index` | `int` | required | patcher filter-stack lookup |
| `property` | `str` | required | MLT `<property name=...>` attribute |
| `keyframes` | `str` (JSON list) | required | parsed to `list[Keyframe]` |
| `mode` | `str` ∈ `{"replace","merge"}` | optional (default `"replace"`) | merge branch selector |

### Return-dict fields (per keyframe tool)

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `status` | `"success"\|"error"` | required | caller |
| `data.project_file` | `str` | required on success | — |
| `data.track` | `int` | required on success | — |
| `data.clip` | `int` | required on success | — |
| `data.effect_index` | `int` | required on success | — |
| `data.property` | `str` | required on success | — |
| `data.keyframes_written` | `str` (MLT animation string) | required on success | evidence of write |
| `data.snapshot_id` | `str` | required on success | audit trail |

### `effect_find` return-dict

| Field | Type | Required |
|-------|------|----------|
| `data.effect_index` | `int` | required |

### Resource / boundary limits
- No new config or quotas.
- FPS: read from `project.profile.fps` every call (NOT cached).

## Verification Commands

- **Build:** not configured.
- **Tests:** `uv run pytest tests/integration/test_keyframe_mcp_tools.py tests/ -v`
- **Acceptance:**
  - Unit & integration tests (above command).
  - Manual end-to-end (master spec Verification §3-§6): open the written `.kdenlive` in Kdenlive 25.x and confirm animation renders.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:3665-3723` (`effect_add`) — snapshot→parse→apply→serialize sequence, error envelope.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:22-49` (`_ok`, `_err`, `_require_workspace`) — response helpers.
- `tests/integration/test_mcp_tools.py` — existing integration-test style for MCP tools (pattern to mirror).

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Register four new `@mcp.tool()` functions. |
| `tests/integration/test_keyframe_mcp_tools.py` | Create | Integration tests against fixture. |
| `tests/integration/fixtures/keyframe_project.kdenlive` | Create | Minimal fixture with transform filter on clip. |
