---
type: phase-spec
master_spec: /home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-masking.md
sub_spec_number: 2
title: Alpha Routing Logic (mask_start / mask_apply sandwich)
date: 2026-04-13
dependencies: [1, "Spec 1 (patcher — shipped)"]
---

# Sub-Spec 2: Alpha Routing Logic

Refined from `docs/specs/2026-04-13-masking.md`.

## CRITICAL ESCALATION RESOLUTION

The master spec assumed Kdenlive routes alpha via "stack order + `alpha_operation` property on the target filter." **This is incorrect.**

Direct inspection of `/usr/share/kdenlive/effects/mask_start.xml`, `mask_start_rotoscoping.xml`, and `mask_apply.xml` confirms Kdenlive uses a **three-filter sandwich**:

```
[ mask_start-<variant> ]   ← snapshots the frame; embeds the mask filter via filter.* nested properties
[ intermediate filter 1 ]  ← the effect(s) to be bounded by the mask
[ intermediate filter N ]
[ mask_apply ]             ← composites the masked result back over the snapshot via qtblend transition
```

Key source evidence:
- `mask_start.xml`: "This filter works in conjunction with the mask_apply filter ... makes a snapshot of the frame before applying a filter ... mask_apply uses a transition to composite."
- `mask_start_rotoscoping.xml`: carries `<parameter type="fixed" name="filter" value="rotoscoping">` and `filter.spline`, `filter.alpha_operation`, `filter.feather`, `filter.feather_passes` — i.e., the rotoscoping parameters are embedded as properties prefixed `filter.` on the `mask_start-rotoscoping` filter.
- `mask_apply.xml`: carries `<parameter type="fixed" name="transition" default="qtblend" value="qtblend">`.

**This invalidates the master spec's implied "single filter + target-property" model.** The refined implementation follows the sandwich pattern, with `apply_mask_to_effect` doing the wrapping rather than merely reordering.

Per the master spec's escalation rules (lines 31-33 and 197-198), this discovery was an anticipated trigger: "If Kdenlive's rotoscoping filter uses a fundamentally different alpha-routing mechanism than 'stack order + alpha_operation property' — stop, inspect, report." Report: this phase spec. Proceed with sandwich implementation.

## Scope

Extend `pipelines/masking.py` with:
- `build_mask_start_rotoscoping_xml(clip_ref, params) -> str` — emits a `mask_start` filter variant wrapping rotoscoping parameters (uses `filter.*` prefixed properties).
- `build_mask_apply_xml(clip_ref) -> str` — emits a `mask_apply` filter with the `qtblend` transition property.
- `apply_mask_to_effect(project, clip_ref, mask_effect_index, target_effect_index) -> dict` — converts a plain rotoscoping filter (inserted by Sub-Spec 1) into the full sandwich around the target filter. Inserts a `mask_apply` filter below the target if one is not already present, and converts the mask filter from `rotoscoping` to `mask_start-rotoscoping` (carrying `filter.*` properties) if not already converted.

Also create a Kdenlive-authored reference fixture to validate the sandwich shape against real Kdenlive output.

## Interface Contracts

### Provides (consumed by Sub-Spec 3)
- `apply_mask_to_effect(project, clip_ref, mask_effect_index, target_effect_index) -> dict` returning `{"reordered": bool, "mask_effect_index": int, "target_effect_index": int, "mask_apply_effect_index": int, "converted_to_sandwich": bool}`.
- `build_mask_start_rotoscoping_xml(clip_ref: tuple[int,int], params: MaskParams) -> str`
- `build_mask_apply_xml(clip_ref: tuple[int,int]) -> str`
- Constants: `MASK_START_SERVICES = ("mask_start",)`, `MASK_APPLY_SERVICE = "mask_apply"`, `MASK_CAPABLE_INNER_SERVICES = ("rotoscoping", "frei0r.alpha0ps_alphaspot", "shape")`.

### Requires
- Sub-Spec 1: `MaskParams`, `ALPHA_OPERATION_TO_MLT`, existing `build_rotoscoping_xml` (for the non-sandwich fast path).
- `patcher.list_effects`, `patcher.insert_effect_xml`, `patcher.reorder_effects`, `patcher.set_effect_property`, `patcher._iter_clip_filters` — all shipped.

### Shared State
None. Mutates `project.opaque_elements` via `patcher` calls only — no filesystem I/O.

## Implementation Steps

### Step 1: Create reference fixture
- **File:** `tests/unit/fixtures/masking_reference.kdenlive`
- **Action:** create
- **Method:** Hand-author a minimal Kdenlive XML containing a tractor with one track, one producer, one clip, and a three-filter sandwich (`mask_start-rotoscoping` → `brightness` → `mask_apply`) with `filter.*` properties and `transition=qtblend`. Use `/usr/share/kdenlive/effects/mask_start_rotoscoping.xml` as the authority for property names. If a real Kdenlive 25.x sample can be opened in the app and saved with a rotoscoping mask, prefer that; otherwise the hand-authored fixture derived directly from the XML effect definitions is acceptable and explicitly permitted by the master spec (line 104: "OR hand-craft minimal XML matching Kdenlive's output format").
- **Properties the fixture MUST contain on the `mask_start-rotoscoping` filter:**
  - `<property name="mlt_service">mask_start</property>`
  - `<property name="kdenlive_id">mask_start-rotoscoping</property>`
  - `<property name="filter">rotoscoping</property>` (the fixed wrapper declaration)
  - `<property name="filter.spline">{json}</property>`
  - `<property name="filter.mode">alpha</property>`
  - `<property name="filter.alpha_operation">clear</property>`
  - `<property name="filter.feather">0</property>`
  - `<property name="filter.feather_passes">1</property>`
- **Properties the `mask_apply` filter MUST contain:**
  - `<property name="mlt_service">mask_apply</property>`
  - `<property name="kdenlive_id">mask_apply</property>`
  - `<property name="transition">qtblend</property>`

### Step 2: Write failing test file
- **File:** `tests/unit/test_masking_alpha_routing.py`
- **Pattern:** follow `tests/unit/test_stack_ops_pipeline.py` — use `parse_project` on the fixture; build a `KdenliveProject` in memory where needed.
- **Tests:**
  - `test_exports_present` — `apply_mask_to_effect`, `build_mask_start_rotoscoping_xml`, `build_mask_apply_xml`.
  - `test_mask_start_xml_matches_kdenlive_convention` — build XML, parse, assert all eight `filter.*` properties above exist.
  - `test_mask_apply_xml_has_qtblend` — assert `transition=qtblend`.
  - `test_reference_fixture_parses` — fixture loads via `parse_project`; `patcher.list_effects` returns 3 filters with services `["mask_start","<inner>","mask_apply"]`.
  - `test_apply_mask_already_ordered` — mask_index=0, target_index=1: expect `reordered=False`, `converted_to_sandwich=True` (first call always converts), a `mask_apply` filter now exists at index 2.
  - `test_apply_mask_needs_reorder` — mask_index=2, target_index=0: reorders so mask is above target; returns `reordered=True`.
  - `test_apply_mask_out_of_range` — `IndexError` naming stack length.
  - `test_apply_mask_wrong_service` — mask_effect_index points to e.g. `brightness`: raises `ValueError` with actual service name, listing valid inner services.
  - `test_apply_mask_idempotent` — calling `apply_mask_to_effect` twice with the same args leaves the sandwich intact; second call returns `converted_to_sandwich=False` and does NOT add a second `mask_apply`.
- **Run:** `uv run pytest tests/unit/test_masking_alpha_routing.py -v`
- **Expected:** all FAIL.

### Step 3: Implement `build_mask_start_rotoscoping_xml`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py`
- **Action:** modify (extend)
- Emit a `<filter>` with `mlt_service="mask_start"`, `track=`, `clip_index=`, and the property set listed in Step 1 above. Reuse the `spline` JSON encoding from Sub-Spec 1 but write it to `filter.spline`. Reuse `ALPHA_OPERATION_TO_MLT` on `filter.alpha_operation`.

### Step 4: Implement `build_mask_apply_xml`
- **File:** same module
- Emit `<filter mlt_service="mask_apply" track=".." clip_index="..">` with `mlt_service`, `kdenlive_id=mask_apply`, and `transition=qtblend` properties. No other parameters.

### Step 5: Implement `apply_mask_to_effect`
- **File:** same module
- **Algorithm:**
  1. Call `patcher.list_effects(project, clip_ref)` → `filters`.
  2. Validate `mask_effect_index` and `target_effect_index` in range `[0, len(filters))`; on failure raise `IndexError(f"index {i} out of range (clip has {len(filters)} filters)")`.
  3. Let `mask_filter = filters[mask_effect_index]`. If `mask_filter["mlt_service"] not in ("rotoscoping", "mask_start", *MASK_CAPABLE_INNER_SERVICES)`, raise `ValueError(f"effect at index {mask_effect_index} has service {svc!r}; expected one of {valid}")`.
  4. **Conversion step:** If `mask_filter["mlt_service"] == "rotoscoping"` (not yet in sandwich form), read its current properties (`spline`, `alpha_operation`, `feather`, `feather_passes`, `mode`), remove the old filter from `project.opaque_elements`, and insert a newly-built `mask_start-rotoscoping` XML at the same index. Mark `converted_to_sandwich=True`.
  5. **mask_apply ensuring:** Refresh `filters = patcher.list_effects(...)`. If no existing `mask_apply` filter at an index > target's index, insert one at `target_effect_index + 1` (refreshed) via `patcher.insert_effect_xml(project, clip_ref, build_mask_apply_xml(clip_ref), position=target_effect_index+1)`. If already present, record its index but do not add another.
  6. **Reorder step:** Refresh filters. If `mask_effect_index >= target_effect_index`, call `patcher.reorder_effects(project, clip_ref, from_index=mask_effect_index, to_index=target_effect_index)` so the mask is immediately above the target. Set `reordered=True`.
  7. Refresh filters once more. Find the final indices of mask and target (they may have shifted after inserts/reorders). Find the `mask_apply` index.
  8. Return `{"reordered": reordered, "mask_effect_index": <new>, "target_effect_index": <new>, "mask_apply_effect_index": <mask_apply_idx>, "converted_to_sandwich": converted}`.

### Step 6: Document alpha routing in module docstring
- **File:** same module
- **Action:** modify — extend the module docstring to explain:
  > Kdenlive routes mask alpha via a three-filter sandwich: `mask_start-<variant>` + intermediate effect(s) + `mask_apply`. The `mask_start` filter embeds inner filter params via `filter.*` prefixed properties and snapshots the frame; `mask_apply` composites the masked result back via a `qtblend` transition. See `docs/specs/2026-04-13-masking/index.md` for the confirmation trail.

### Step 7: Run tests
- **Run:** `uv run pytest tests/unit/test_masking_alpha_routing.py -v`
- **Expected:** all PASS.

### Step 8: Run full suite and commit
- **Run:** `uv run pytest tests/ -v`
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py tests/unit/test_masking_alpha_routing.py tests/unit/fixtures/masking_reference.kdenlive`
- **Message:** `feat: mask alpha routing via mask_start/mask_apply sandwich (sub-spec 2)`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `apply_mask_to_effect` returning the dict shape defined in interface contract.
- `[BEHAVIORAL]` mask_index < target_index already → `reordered=False` (but `converted_to_sandwich=True` on first invocation).
- `[BEHAVIORAL]` mask_index >= target_index → reorders via `patcher.reorder_effects` so mask precedes target; `reordered=True`.
- `[BEHAVIORAL]` Out-of-range indices raise `IndexError` naming current stack length.
- `[BEHAVIORAL]` Mask filter whose service is not rotoscoping/mask_start/alpha0ps_alphaspot/shape raises `ValueError` listing the actual service name and the valid services.
- `[BEHAVIORAL]` **Amended from master spec:** Instead of setting a property on the target filter for alpha routing, the function wraps the mask+target in the `mask_start` / `mask_apply` sandwich. Module docstring documents this, and the test `test_apply_mask_already_ordered` confirms the resulting filter stack contains `mask_start` → target → `mask_apply`.
- `[BEHAVIORAL]` Idempotent: second call leaves stack unchanged, returns `converted_to_sandwich=False`.
- `[MECHANICAL]` `uv run pytest tests/unit/test_masking_alpha_routing.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` passes (no regressions).

## Completeness Checklist

### `mask_start-rotoscoping` required properties (confirmed against `/usr/share/kdenlive/effects/mask_start_rotoscoping.xml`)
| Property | Required | Value |
|----------|----------|-------|
| `mlt_service` | required | `mask_start` |
| `kdenlive_id` | required | `mask_start-rotoscoping` |
| `filter` | required | `rotoscoping` (fixed value) |
| `filter.spline` | required | JSON point list |
| `filter.mode` | required | `alpha` \| `luma` \| `rgb` (default `alpha`) |
| `filter.alpha_operation` | required | `clear` \| `max` \| `min` \| `add` \| `sub` |
| `filter.invert` | optional | `0` \| `1` |
| `filter.feather` | required | int 0-500 |
| `filter.feather_passes` | required | int 1-20 |

### `mask_apply` required properties
| Property | Required | Value |
|----------|----------|-------|
| `mlt_service` | required | `mask_apply` |
| `kdenlive_id` | required | `mask_apply` |
| `transition` | required | `qtblend` (fixed) |

### `apply_mask_to_effect` return dict
| Key | Type | Always present |
|-----|------|----------------|
| `reordered` | bool | yes |
| `mask_effect_index` | int | yes (post-operation) |
| `target_effect_index` | int | yes (post-operation) |
| `mask_apply_effect_index` | int | yes |
| `converted_to_sandwich` | bool | yes |

## Verification Commands

- **Build:** `uv sync`
- **Unit tests:** `uv run pytest tests/unit/test_masking_alpha_routing.py -v`
- **Full suite:** `uv run pytest tests/ -v`
- **Manual:** open `tests/unit/fixtures/masking_reference.kdenlive` in Kdenlive 25.x — confirm the rotoscoping mask is editable and `mask_apply` does not error.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` — already mutates via `patcher.insert_effect_xml` and `reorder_effects`; mirror that style (no direct `opaque_elements` manipulation here either; use patcher APIs exclusively).
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` lines 964-1070 — `insert_effect_xml` and `reorder_effects` signatures.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py` | Modify | Add `build_mask_start_rotoscoping_xml`, `build_mask_apply_xml`, `apply_mask_to_effect` |
| `tests/unit/test_masking_alpha_routing.py` | Create | Alpha routing unit tests |
| `tests/unit/fixtures/masking_reference.kdenlive` | Create | Reference Kdenlive fixture with sandwich |
