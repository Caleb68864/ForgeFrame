---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-wrappers.md"
sub_spec_number: 3
title: "Semantic Reorder Wrappers + Integration"
date: 2026-04-13
dependencies: [1, 2]
---

# Sub-Spec 3: Semantic Reorder Wrappers + Integration

Refined from `docs/specs/2026-04-13-effect-wrappers.md`.

## Scope

Hand-write four trivial reorder wrappers (`move_to_top`, `move_to_bottom`, `move_up`, `move_down`) in `server/tools.py`. Each delegates to `patcher.reorder_effects`. Run final full-suite regression as the integration gate for the entire spec.

## Interface Contracts

### Provides
- `server.tools.move_to_top(workspace_path, project_file, track, clip, effect_index) -> dict` — `@mcp.tool()`.
- `server.tools.move_to_bottom(workspace_path, project_file, track, clip, effect_index) -> dict` — `@mcp.tool()`.
- `server.tools.move_up(workspace_path, project_file, track, clip, effect_index) -> dict` — `@mcp.tool()`.
- `server.tools.move_down(workspace_path, project_file, track, clip, effect_index) -> dict` — `@mcp.tool()`.

Master-spec contract (line 149) specifies signature `(workspace_path: str, project_file: str, track: int, clip: int, effect_index: int) -> dict`. Include `project_file` even if most existing tools elide it; verify against peers in `tools.py` and omit if inconsistent with project conventions — document in commit.

### Requires
- From Sub-Spec 1: `_ok`, `_err`, `_require_workspace` from `tools_helpers`.
- Shipped: `patcher.reorder_effects` (`adapters/kdenlive/patcher.py:1028`), `patcher.list_effects` (line 874), `create_snapshot`.

### Shared State
- Each reorder call takes exactly one snapshot.

## Implementation Steps

### Step 1: Write failing tests
- **File:** `tests/integration/test_reorder_wrappers.py`
- **Tests:**
  - `test_move_to_top_moves_filter_to_index_0` — on 4-filter stack, `move_to_top(effect_index=3)` → `list_effects` shows former-last at index 0.
  - `test_move_to_bottom_moves_filter_to_last_index`.
  - `test_move_up_decrements_index`.
  - `test_move_up_at_top_is_noop_with_note` — `effect_index=0`, assert `data.note == "already at top"` and `effect_index_before == effect_index_after`.
  - `test_move_down_increments_index`.
  - `test_move_down_at_bottom_is_noop_with_note`.
  - `test_out_of_range_effect_index_returns_err_with_stack_length` — `_err` message contains current stack length.
  - `test_single_filter_stack_all_four_are_noops`.
  - `test_each_write_returns_valid_snapshot_id` — `snapshot_id` exists on disk in the workspace's snapshot store.
- **Run:** `uv run pytest tests/integration/test_reorder_wrappers.py -v`
- **Expected:** FAIL.

### Step 2: Implement the four wrappers
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Action:** modify (append four `@mcp.tool()` functions)
- **Shared helper (module-local):**
  ```python
  def _reorder_impl(workspace_path, track, clip, effect_index, compute_to, noop_note):
      try:
          ws_path, ws = _require_workspace(workspace_path)
          # load project; compute current stack length via list_effects
          # if out-of-range → _err with stack length
          # if compute_to is None (meaning already at edge) → snapshot + _ok with note
          # else snapshot, patcher.reorder_effects, serialize, _ok
          ...
      except (ValueError, IndexError, FileNotFoundError) as exc:
          return _err(str(exc))
  ```
- Each of the four wrappers is ~6 lines delegating to `_reorder_impl` with a specific `compute_to` lambda:
  - `move_to_top`: `compute_to = lambda i, n: 0 if i > 0 else None` (None → already at top)
  - `move_to_bottom`: `compute_to = lambda i, n: n - 1 if i < n - 1 else None`
  - `move_up`: `compute_to = lambda i, n: i - 1 if i > 0 else None`
  - `move_down`: `compute_to = lambda i, n: i + 1 if i < n - 1 else None`

### Step 3: Verify tests pass
- **Run:** `uv run pytest tests/integration/test_reorder_wrappers.py -v`
- **Expected:** PASS.

### Step 4: Full-suite regression (integration gate for entire spec)
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS with no regressions vs the pre-spec baseline (2552 tests + new tests from Sub-Specs 1/2/3).

### Step 5: Manual smoke verification
- Apply `effect_add` 4 times to a clip, then call `move_to_top(effect_index=3)`; open in Kdenlive 25.x and confirm filter position in the effect stack panel.

### Step 6: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_reorder_wrappers.py`
- **Message:** `feat: semantic reorder wrappers (move_to_top / move_to_bottom / move_up / move_down)`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `move_to_top`, `move_to_bottom`, `move_up`, `move_down` via `@mcp.tool()`.
- `[STRUCTURAL]` Each signature matches master spec line 149.
- `[STRUCTURAL]` Return shape: `{"status", "data": {"effect_index_before", "effect_index_after", "snapshot_id"}}` (plus optional `note` on no-ops).
- `[INTEGRATION]` All four tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` `move_to_top(effect_index=3)` on 4-filter stack moves to index 0.
- `[BEHAVIORAL]` `move_to_bottom(effect_index=0)` on 4-filter stack moves to index 3.
- `[BEHAVIORAL]` `move_up(effect_index=2)` → index 1; `move_up(effect_index=0)` → `_ok` with note `"already at top"` and equal before/after.
- `[BEHAVIORAL]` `move_down(effect_index=0)` → index 1; `move_down` at last index → `_ok` with note `"already at bottom"`.
- `[BEHAVIORAL]` Out-of-range `effect_index` → `_err` listing current stack length.
- `[BEHAVIORAL]` Each write returns a `snapshot_id` that exists on disk.
- `[MECHANICAL]` `uv run pytest tests/integration/test_reorder_wrappers.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

## Completeness Checklist

### Reorder return shape

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| status | str | required | clients |
| data.effect_index_before | int | required | verification / undo UIs |
| data.effect_index_after | int | required | chaining |
| data.snapshot_id | str | required | undo |
| data.note | str | optional (present on no-op) | clients displaying "already at top/bottom" |
| message | str | required (on error) | clients |

### Edge-case expected notes (exact strings)

- `move_to_top` at index 0: `"already at top"`
- `move_up` at index 0: `"already at top"`
- `move_to_bottom` at last index: `"already at bottom"`
- `move_down` at last index: `"already at bottom"`
- Single-filter stack: whichever applies per the above.

### Boundaries

- `effect_index < 0` or `effect_index >= len(stack)` → `_err(f"effect_index {i} out of range (stack has {n} filters)")`.

## Verification Commands

- **Build:** `uv sync`.
- **Tests:**
  - `uv run pytest tests/integration/test_reorder_wrappers.py -v`
  - `uv run pytest tests/ -v` (full regression — THIS IS THE INTEGRATION GATE for the spec)
- **Smoke:** Apply → reorder → open in Kdenlive, confirm visual order.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:1028` — `reorder_effects` signature (`from_index`, `to_index`).
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:874` — `list_effects` for stack-length lookup.
- Existing `@mcp.tool()` patterns in `server/tools.py` around `clip_split` (line 1989) for workspace-load / patch / serialize / `_ok` flow.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Append 4 reorder wrappers + shared `_reorder_impl` |
| `tests/integration/test_reorder_wrappers.py` | Create | Reorder wrapper integration tests |
