---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-ops.md"
sub_spec_number: 1
title: "Patcher Stack-Mutation Extensions"
date: 2026-04-13
dependencies: []
---

# Sub-Spec 1: Patcher Stack-Mutation Extensions

Refined from `docs/specs/2026-04-13-stack-ops.md` — Stack-Ops feature.

## Scope

Add three additive functions to `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`:

- `insert_effect_xml(project, clip_ref, xml_string, position) -> None`
- `remove_effect(project, clip_ref, effect_index) -> None`
- `reorder_effects(project, clip_ref, from_index, to_index) -> None`

These mutate `project.opaque_elements` in place. They MUST reuse the existing private helper `_iter_clip_filters` (patcher.py:828) to discover per-clip filter positions and MUST NOT modify Spec 1's already-shipped methods (`get_effect_property`, `set_effect_property`, `list_effects`).

Filter elements are stored as `OpaqueElement(tag="filter", xml_string=..., position_hint="after_tractor")` (see patcher.py:725-738). Stack order within a clip is the insertion order in `project.opaque_elements` filtered by matching `track=`/`clip_index=` attributes.

Inserts MUST set `position_hint="after_tractor"` so the serializer places the element correctly. The supplied `xml_string` is treated verbatim — the caller is responsible for providing well-formed `<filter ...>` XML (Sub-Spec 2 supplies it via `apply_paste`).

## Interface Contracts

### Provides
- `insert_effect_xml(project: KdenliveProject, clip_ref: tuple[int, int], xml_string: str, position: int) -> None` — inserts a new filter `OpaqueElement` into `project.opaque_elements` such that, when re-iterated by `_iter_clip_filters`, it occupies stack-index `position` (0 = top of stack, `len(stack)` = bottom).
- `remove_effect(project: KdenliveProject, clip_ref: tuple[int, int], effect_index: int) -> None` — removes the filter at the given per-clip stack index from `project.opaque_elements`.
- `reorder_effects(project: KdenliveProject, clip_ref: tuple[int, int], from_index: int, to_index: int) -> None` — moves a filter within a clip's stack. `from_index == to_index` is a no-op.

All three raise `IndexError` with a message naming the current stack length on out-of-range arguments. None of them touch filters belonging to other clips.

### Requires
- From Spec 1 (shipped): `_iter_clip_filters` at patcher.py:828 — used to enumerate the absolute `project.opaque_elements` indices that belong to this clip's stack.

### Shared State
- `project.opaque_elements: list[OpaqueElement]` — only filter elements matching the target clip are mutated. Other elements (transitions, other clips' filters) are not touched and their relative ordering is preserved.

## Implementation Steps

### Step 1: Write failing test
- **File:** `tests/unit/test_patcher_stack_ops.py` (new)
- **Setup:** Build a minimal `KdenliveProject` in-memory (or load `tests/integration/fixtures/keyframe_project.kdenlive` via `parse_project`) with a clip on track 2 carrying 3 filters.
- **Tests:**
  - `test_insert_effect_xml_at_top` — `position=0` makes the new filter `list_effects(...)[0]`.
  - `test_insert_effect_xml_at_bottom` — `position=len(stack)` appends.
  - `test_insert_effect_xml_middle` — `position=1` lands at index 1, others shift down.
  - `test_remove_effect_middle` — `remove_effect(p, (2,0), 1)` yields `len(list_effects) == 2` and the surviving order matches the original minus index 1.
  - `test_reorder_effects_to_top` — `reorder_effects(p, (2,0), 2, 0)` makes the former index-2 filter the new index-0.
  - `test_reorder_effects_noop` — `from_index == to_index` does not mutate `project.opaque_elements` (compare list identity / contents).
  - `test_insert_invalid_position_raises` — `position=-1` or `position=len(stack)+1` raises `IndexError` whose message contains the current stack length.
  - `test_remove_invalid_index_raises` — `effect_index=99` raises `IndexError` containing the stack length.
  - `test_other_clips_untouched` — Operations on `(2,0)` do not change filter count for `(2,1)` or any other clip.
- **Run:** `uv run pytest tests/unit/test_patcher_stack_ops.py -v`
- **Expected:** all tests FAIL (functions do not exist yet).

### Step 2: Implement `insert_effect_xml`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`
- **Action:** modify (append below `set_effect_property`)
- **Pattern:** Follow the OpaqueElement construction at patcher.py:725-738 (`tag="filter"`, `position_hint="after_tractor"`).
- **Algorithm:**
  1. Call `filters = _iter_clip_filters(project, clip_ref)` to validate `clip_ref` and obtain `(effect_index, opaque_element, parsed_root)` triples.
  2. Validate `0 <= position <= len(filters)`. Else raise `IndexError(f"position {position} out of range (clip has {len(filters)} filters)")`.
  3. Build the new `OpaqueElement(tag="filter", xml_string=xml_string, position_hint="after_tractor")`.
  4. Compute the absolute insertion index in `project.opaque_elements`:
     - If `position < len(filters)`: insert just before the existing element currently at that stack-index — use `project.opaque_elements.index(filters[position][1])`.
     - If `position == len(filters)`: insert just after the last filter currently in this clip's stack — `project.opaque_elements.index(filters[-1][1]) + 1`. If the stack is empty, append to the end of `project.opaque_elements`.
  5. `project.opaque_elements.insert(abs_index, new_element)`.

### Step 3: Implement `remove_effect`
- **File:** patcher.py (same)
- **Action:** modify
- **Algorithm:**
  1. `filters = _iter_clip_filters(project, clip_ref)`.
  2. Validate `0 <= effect_index < len(filters)`; else raise `IndexError` naming `len(filters)`.
  3. `target_elem = filters[effect_index][1]`; `project.opaque_elements.remove(target_elem)`.

### Step 4: Implement `reorder_effects`
- **File:** patcher.py (same)
- **Action:** modify
- **Algorithm:**
  1. If `from_index == to_index`: return immediately (no-op).
  2. `filters = _iter_clip_filters(project, clip_ref)`.
  3. Validate both indices are in `[0, len(filters))`; else raise `IndexError` naming `len(filters)`.
  4. `moving = filters[from_index][1]`.
  5. `project.opaque_elements.remove(moving)`.
  6. Re-iterate after removal to find new absolute insertion target:
     - `filters_after = _iter_clip_filters(project, clip_ref)` (now `len-1`).
     - If `to_index < len(filters_after)`: `abs_index = project.opaque_elements.index(filters_after[to_index][1])`.
     - Else (`to_index == len(filters_after)` after removal, i.e. moving to bottom): `abs_index = project.opaque_elements.index(filters_after[-1][1]) + 1` (if list non-empty) else append.
  7. `project.opaque_elements.insert(abs_index, moving)`.

### Step 5: Verify tests pass
- **Run:** `uv run pytest tests/unit/test_patcher_stack_ops.py -v`
- **Expected:** all tests PASS.

### Step 6: Verify Spec 1 regressions
- **Run:** `uv run pytest tests/ -v -k "patcher or keyframe or effect"`
- **Expected:** no Spec 1 tests broken.

### Step 7: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py tests/unit/test_patcher_stack_ops.py`
- **Message:** `feat: patcher stack-mutation extensions (insert/remove/reorder)`

## Acceptance Criteria

- `[STRUCTURAL]` `patcher.py` exports `insert_effect_xml(project, clip_ref, xml_string: str, position: int) -> None`.
- `[STRUCTURAL]` `patcher.py` exports `remove_effect(project, clip_ref, effect_index: int) -> None`.
- `[STRUCTURAL]` `patcher.py` exports `reorder_effects(project, clip_ref, from_index: int, to_index: int) -> None`.
- `[BEHAVIORAL]` `insert_effect_xml` with `position=0` places the filter at the top of the clip's stack; `position=len(stack)` places it at the bottom; absolute position within `project.opaque_elements` is computed correctly relative to the `after_tractor` placement slot used by `_apply_add_effect`.
- `[BEHAVIORAL]` `remove_effect(project, (2,0), 1)` removes the second filter; `list_effects` after removal returns `len-1` entries with stable remaining order.
- `[BEHAVIORAL]` `reorder_effects(project, (2,0), 2, 0)` moves the third filter to the top; `list_effects` verifies new order.
- `[BEHAVIORAL]` Out-of-range `effect_index` or invalid `position` raises `IndexError` with message naming current stack length.
- `[BEHAVIORAL]` `reorder_effects` with `from_index == to_index` is a no-op.
- `[MECHANICAL]` `uv run pytest tests/unit/test_patcher_stack_ops.py -v` passes.

## Completeness Checklist

Function signatures created:

| Function | Args | Returns | Raises |
|----------|------|---------|--------|
| `insert_effect_xml` | `project, clip_ref: tuple[int,int], xml_string: str, position: int` | `None` | `IndexError` on bad `clip_ref` (via `_iter_clip_filters`) or out-of-range `position` |
| `remove_effect` | `project, clip_ref: tuple[int,int], effect_index: int` | `None` | `IndexError` on bad `clip_ref` or out-of-range `effect_index` |
| `reorder_effects` | `project, clip_ref: tuple[int,int], from_index: int, to_index: int` | `None` | `IndexError` on bad `clip_ref` or either index out of range |

Invariants:
- All inserts use `position_hint="after_tractor"`.
- `OpaqueElement.tag` for inserted filters is `"filter"`.
- Filters belonging to other clips never change relative order.

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_patcher_stack_ops.py -v`
- **Regression:** `uv run pytest tests/ -v`
- **Acceptance:** the unit tests above directly assert each `[BEHAVIORAL]` criterion.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:725-738` — `_apply_add_effect` shows the canonical filter-`OpaqueElement` shape (tag, xml_string, position_hint).
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:828-871` — `_iter_clip_filters` is the only sanctioned read path; do NOT duplicate XML traversal.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:907-948` — `get_effect_property` / `set_effect_property` show the IndexError message style ("`effect_index N out of range (clip has K filters)`") to match.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` | Modify | Append three new functions below `set_effect_property`. |
| `tests/unit/test_patcher_stack_ops.py` | Create | Unit tests for the three new functions. |
