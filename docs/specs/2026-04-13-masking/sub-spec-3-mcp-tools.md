---
type: phase-spec
master_spec: /home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-masking.md
sub_spec_number: 3
title: MCP Tool Surface + Integration
date: 2026-04-13
dependencies: [1, 2]
---

# Sub-Spec 3: MCP Tool Surface + Integration

Refined from `docs/specs/2026-04-13-masking.md`.

## Scope

Register six MCP tools in `server/tools.py` that wrap the masking pipeline (Sub-Specs 1 and 2) into workspace-aware, snapshot-creating, JSON-envelope-returning callables. Follow the exact pattern used by existing effect tools (`effect_add`, `effect_reorder`) including the `_ok` / `_err` envelope, `_require_workspace`, `create_snapshot` → `parse_project` → mutate → `serialize_project` flow.

## Interface Contracts

### Provides (consumed by end users / MCP clients)
All six tools accept `workspace_path: str, project_file: str` as their first two params, create a snapshot, and return a `_ok` envelope containing `snapshot_id`:

- `mask_set(workspace_path, project_file, track, clip, type: str, params: str) -> dict`
- `mask_set_shape(workspace_path, project_file, track, clip, shape: str, bounds: str = "", points: str = "", feather: int = 0, alpha_operation: str = "clear") -> dict`
- `mask_apply(workspace_path, project_file, track, clip, mask_effect_index: int, target_effect_index: int) -> dict`
- `effect_chroma_key(workspace_path, project_file, track, clip, color: str = "#00FF00", tolerance: float = 0.15, blend: float = 0.0) -> dict`
- `effect_chroma_key_advanced(workspace_path, project_file, track, clip, color: str, tolerance_near: float, tolerance_far: float, edge_smooth: float = 0.0, spill_suppression: float = 0.0) -> dict`
- `effect_object_mask(workspace_path, project_file, track, clip, enabled: bool = True, threshold: float = 0.5) -> dict`

### Requires
- Sub-Spec 1: `build_*_xml` functions, `MaskParams`, `MaskShape`, `shape_to_points`, `color_to_mlt_hex`.
- Sub-Spec 2: `apply_mask_to_effect`, `build_mask_start_rotoscoping_xml`, `build_mask_apply_xml`.
- `patcher.insert_effect_xml`, `patcher.list_effects`.
- `workspace.create_snapshot`, `parse_project`, `serialize_project`.

### Shared State
- `server/tools.py` global `mcp` FastMCP instance — use `@mcp.tool()` decorator per existing pattern.

## Implementation Steps

### Step 1: Write failing integration tests
- **File:** `tests/integration/test_masking_mcp_tools.py`
- **Pattern:** look for existing patterns in `tests/integration/` (e.g. any `test_effect_*` integration test, or follow the `effect_add` end-to-end test if present). If none, follow `tests/unit/test_effect_apply.py` and use `_require_workspace` tooling to set up a temporary workspace with a valid Kdenlive project. A reusable fixture already exists at `tests/unit/fixtures/masking_reference.kdenlive` (from Sub-Spec 2) plus whatever existing Kdenlive fixtures live under `tests/`.
- **Tests to add:**
  - `test_all_six_tools_importable` — `from workshop_video_brain.edit_mcp.server import tools; for name in (...): assert callable(getattr(tools, name))`.
  - `test_mask_set_shape_rect_end_to_end` — call with `shape="rect"`, `bounds="[0.2,0.2,0.6,0.6]"`; re-parse project; assert effect_index 0 is a rotoscoping filter (or `mask_start-rotoscoping` — see note below) with the expected 4-point spline.
  - `test_mask_set_shape_ellipse_has_32_points` — assert 32 points in the emitted `spline` JSON.
  - `test_mask_set_shape_polygon_passthrough` — `points="[[0.1,0.1],[0.5,0.1],[0.3,0.5]]"`; assert exactly those 3 points.
  - `test_mask_apply_sandwich_end_to_end` — call `mask_set_shape` (rect) → `effect_add` (brightness) → `mask_apply(mask=0, target=1)`; assert final stack has services `["mask_start","<brightness>","mask_apply"]`.
  - `test_mask_apply_reorders` — set up stack where mask index > target index; call `mask_apply`; assert `reordered=true`.
  - `test_effect_chroma_key_emits_canonical_hex` — call with `color="#00FF00"`; re-parse; assert `<property name="key">` == `0x00ff00ff`.
  - `test_effect_chroma_key_invalid_color` — `color="notcolor"` returns `_err` envelope mentioning `#RRGGBB`.
  - `test_effect_chroma_key_advanced_tolerance_ordering` — `tolerance_near=0.5, tolerance_far=0.3` returns `_err` with text "tolerance_far must be >= tolerance_near".
  - `test_snapshot_id_exists_on_disk` — after any mutating call, assert the returned `snapshot_id` corresponds to a directory under `{workspace}/projects/snapshots/`.
  - `test_mask_set_unknown_type` — `type="garbage"` returns `_err` listing `rotoscoping`, `object_mask`, `image_alpha`.
  - `test_mask_set_shape_unknown_shape` — `shape="star"` returns `_err` listing `rect`, `ellipse`, `polygon`.
  - `test_mask_set_image_alpha_not_implemented` — `type="image_alpha"` returns `_err` text "not yet implemented".
- **Run:** `uv run pytest tests/integration/test_masking_mcp_tools.py -v`
- **Expected:** all FAIL.

### Step 2: Append tool module section header in `server/tools.py`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify (append near the bottom, after the stack-presets section)
- Add a section comment block:
  ```
  # ---------------------------------------------------------------------------
  # Masking (spec 2026-04-13-masking)
  # ---------------------------------------------------------------------------
  ```

### Step 3: Implement `mask_set`
- **File:** same
- **Pattern:** mirror `effect_add` (lines 3666-3723).
- **Logic:**
  1. Validate `type in ("rotoscoping","object_mask","image_alpha")` — else `_err` listing the three valid types.
  2. If `type == "image_alpha"` return `_err("image_alpha mask type not yet implemented — use type='rotoscoping' or 'object_mask'")`.
  3. Parse `params` JSON; build a `MaskParams` (if `rotoscoping`) or dict (if `object_mask`) — catch `ValidationError` → `_err`.
  4. Snapshot, parse_project, build appropriate XML via Sub-Spec 1 builder.
  5. Call `patcher.insert_effect_xml(project, (track, clip), xml, position=0)`.
  6. serialize, return `_ok({"effect_index": 0, "type": type, "snapshot_id": snapshot_id})`.

### Step 4: Implement `mask_set_shape`
- **File:** same
- **Logic:**
  1. Parse `bounds` (JSON list) and `points` (JSON list). Either may be empty string.
  2. Build a `MaskShape(kind=shape, bounds=tuple(bounds) if bounds else (0,0,1,1), points=tuple(map(tuple, points)))`.
  3. Call `shape_to_points(shape)` → point list.
  4. Build `MaskParams(points=..., feather=feather, alpha_operation=alpha_operation)`.
  5. Delegate to the same insertion path as `mask_set` with `type="rotoscoping"`.
  6. On `ValueError` / `ValidationError` → `_err(str(exc))`.
  7. Invalid `shape` value → `_err` listing `rect`, `ellipse`, `polygon`.

### Step 5: Implement `mask_apply`
- **File:** same
- **Logic:**
  1. Snapshot, parse_project.
  2. Call `apply_mask_to_effect(project, (track, clip), mask_effect_index, target_effect_index)`.
  3. Catch `IndexError` / `ValueError` → `_err` including the message. For `IndexError`, include `patcher.list_effects(...)` output to aid debugging (mirror `effect_reorder` lines 4466-4473).
  4. Edge case: if `target_effect_index` points to a filter whose `mlt_service in ("mask_start","mask_apply")`, return `_err("cannot mask a mask: target effect is itself a mask filter")`.
  5. serialize, return `_ok({**result, "snapshot_id": snapshot_id})`.

### Step 6: Implement `effect_chroma_key`
- **File:** same
- **Logic:**
  1. Validate color via `color_to_mlt_hex` (catch `ValueError` → `_err` with accepted formats listed).
  2. Snapshot, parse_project.
  3. Build XML via `build_chroma_key_xml`.
  4. `patcher.insert_effect_xml(project, (track, clip), xml, position=<append>)` — position = `len(patcher.list_effects(...))` (i.e. bottom of stack, matching existing `effect_add` behavior).
  5. serialize, return `_ok({"effect_index": new_index, "snapshot_id": snapshot_id})`.

### Step 7: Implement `effect_chroma_key_advanced`
- **File:** same
- **Logic:**
  1. Validate `tolerance_far >= tolerance_near` — else `_err("tolerance_far must be >= tolerance_near")`.
  2. Validate color.
  3. Snapshot, build XML via `build_chroma_key_advanced_xml`, insert, serialize.
  4. Return `_ok({"effect_index": new_index, "snapshot_id": snapshot_id})`.

### Step 8: Implement `effect_object_mask`
- **File:** same
- **Logic:**
  1. Snapshot, parse_project.
  2. Build XML via `build_object_mask_xml(..., {"enabled": enabled, "threshold": threshold})`.
  3. Insert at bottom of stack; serialize.
  4. Return `_ok({"effect_index": new_index, "snapshot_id": snapshot_id})`.
  5. If `effect_catalog.find_by_service("frei0r.alpha0ps_alphaspot")` returns nothing (filter missing from this Kdenlive install), return `_err("object_mask service not available in this Kdenlive install — check /usr/share/kdenlive/effects/")`.

### Step 9: Register all six with `@mcp.tool()`
- Each tool must be decorated `@mcp.tool()` directly above its `def`, matching lines 57, 98, 133, etc. of `server/tools.py`.

### Step 10: Run integration tests
- **Run:** `uv run pytest tests/integration/test_masking_mcp_tools.py -v`
- **Expected:** all PASS.

### Step 11: Full suite
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS with no regressions.

### Step 12: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_masking_mcp_tools.py`
- **Message:** `feat: six masking mcp tools (sub-spec 3)`

## Acceptance Criteria

- `[STRUCTURAL]` All six tools registered with `@mcp.tool()` and importable from `workshop_video_brain.edit_mcp.server.tools`.
- `[STRUCTURAL]` Tool signatures match the interface contracts above (exact parameter names and defaults).
- `[INTEGRATION]` Each write-mutating tool creates a snapshot and returns `snapshot_id` that exists on disk.
- `[BEHAVIORAL]` `mask_set_shape(rect, bounds=[0.2,0.2,0.6,0.6])` inserts rotoscoping filter at effect_index 0.
- `[BEHAVIORAL]` `mask_set_shape(ellipse)` produces 32 spline points.
- `[BEHAVIORAL]` `mask_set_shape(polygon)` preserves the supplied 3 points exactly.
- `[BEHAVIORAL]` End-to-end sandwich: `mask_set_shape` + `effect_add` + `mask_apply` results in the `mask_start` → inner → `mask_apply` triad.
- `[BEHAVIORAL]` `mask_apply` with mask_index > target_index reorders and returns `reordered=true`.
- `[BEHAVIORAL]` `effect_chroma_key(color="#00FF00")` encodes key as `0x00ff00ff`.
- `[BEHAVIORAL]` Invalid color returns `_err` listing accepted formats.
- `[BEHAVIORAL]` `effect_chroma_key_advanced` with `tolerance_near > tolerance_far` returns `_err` with the ordering rule.
- `[BEHAVIORAL]` `mask_set` with unknown `type` returns `_err` listing the three valid types.
- `[BEHAVIORAL]` `mask_set_shape` with unknown `shape` returns `_err` listing `rect`, `ellipse`, `polygon`.
- `[BEHAVIORAL]` `mask_set(type="image_alpha")` returns `_err` with "not yet implemented".
- `[BEHAVIORAL]` `mask_apply` where target is itself a mask filter returns `_err("cannot mask a mask")`.
- `[MECHANICAL]` `uv run pytest tests/integration/test_masking_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` passes with zero regressions.

## Completeness Checklist

### Tool return envelopes
All tools return `_ok` / `_err` JSON envelopes following existing patterns at `server/tools.py` lines 22-28.

| Tool | Success Data Keys |
|------|-------------------|
| `mask_set` | `effect_index`, `type`, `snapshot_id` |
| `mask_set_shape` | `effect_index`, `type`, `snapshot_id` |
| `mask_apply` | `mask_effect_index`, `target_effect_index`, `mask_apply_effect_index`, `reordered`, `converted_to_sandwich`, `snapshot_id` |
| `effect_chroma_key` | `effect_index`, `snapshot_id` |
| `effect_chroma_key_advanced` | `effect_index`, `snapshot_id` |
| `effect_object_mask` | `effect_index`, `snapshot_id` |

### Validation rules
| Rule | Tool | Error message contains |
|------|------|-----------------------|
| normalized coord `[0,1]` | `mask_set_shape` | offending value, "out of [0, 1]" |
| polygon min 3 points | `mask_set_shape` | "at least 3" |
| ellipse min sample_count 4 | `mask_set_shape` | "sample_count must be >= 4" |
| color format | `effect_chroma_key`, `effect_chroma_key_advanced` | "#RRGGBB" |
| tolerance ordering | `effect_chroma_key_advanced` | "tolerance_far must be >= tolerance_near" |
| type whitelist | `mask_set` | "rotoscoping, object_mask, image_alpha" |
| shape whitelist | `mask_set_shape` | "rect, ellipse, polygon" |
| image_alpha deferred | `mask_set` | "not yet implemented" |
| cannot mask a mask | `mask_apply` | "cannot mask a mask" |

## Verification Commands

- **Build:** `uv sync`
- **Integration tests:** `uv run pytest tests/integration/test_masking_mcp_tools.py -v`
- **Full suite:** `uv run pytest tests/ -v`
- **Manual (master spec §Verification):**
  1. `mask_set_shape(rect)` + `effect_add(glow)` + `mask_apply` → open in Kdenlive 25.x; glow is bounded by the rectangle.
  2. `effect_chroma_key` on a green-screen clip; confirm transparency.
  3. `mask_set_shape(ellipse)`; confirm ellipse-shaped mask editable in Kdenlive UI.
  4. Three consecutive `mask_set_shape` calls; confirm three rotoscoping filters in effect stack.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines 3666-3723 (`effect_add`) — the canonical snapshot → parse → mutate → serialize flow.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines 4427-4485 (`effect_reorder`) — `IndexError` handling with stack-length context and snapshot_id pattern.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines 22-28 — `_ok`, `_err` helpers.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` lines 45-55 — `_require_workspace`.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Add six `@mcp.tool()` functions |
| `tests/integration/test_masking_mcp_tools.py` | Create | End-to-end MCP integration tests |
