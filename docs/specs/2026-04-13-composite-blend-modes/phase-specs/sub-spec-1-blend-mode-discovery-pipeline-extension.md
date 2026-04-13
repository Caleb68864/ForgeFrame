---
type: phase-spec
master_spec: "../../2026-04-13-composite-blend-modes.md"
sub_spec_number: 1
title: "Blend Mode Discovery + Pipeline Extension"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 1: Blend Mode Discovery + Pipeline Extension

Refined from spec.md -- Factory Run ff-2026-04-13-composite-blend-modes.

## Scope

Inspect Kdenlive's compositing XML, determine the correct MLT service(s), property name(s), and accepted value set(s) for the 11 abstract blend modes. Build the `BLEND_MODE_TO_MLT` mapping. Extend `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` with `apply_composite`, `BLEND_MODES`, and `BLEND_MODE_TO_MLT`. Pure logic; no MCP surface or serializer work.

### CRITICAL CONTEXT (from Stage 3 codebase analysis)

The base MLT `composite` transition has NO blend-mode property. Blend modes live on TWO separate services:

1. **`frei0r.cairoblend`** -- string-enum blend, property name `"1"` (the parameter number, literally), values from set: `normal, add, saturate, multiply, screen, overlay, darken, lighten, colordodge, colorburn, hardlight, softlight, difference, exclusion, hslhue, hslsaturation, hslcolor, hslluminosity`.
2. **`qtblend`** -- integer-enum blend, property name `compositing`, values from list: `0;11;12;13;14;15;16;17;18;19;20;21;22;23;24;25;26;27;28;29;6;8` with labels `Alpha blend,Xor,Plus,Multiply,Screen,Overlay,Darken,Lighten,Color dodge,Color burn,Hard light,Soft light,Difference,Exclusion,Bitwise or/and/xor/nor/nand/not xor, Destination in, Destination out`.

This triggers three of spec.md's escalation conditions. The recommended mapping table (see Stage 3 memory.md) routes `destination_in`, `destination_out`, `source_over` to `qtblend` and the remaining Cairo-native modes to `frei0r.cairoblend`. `subtract` has NO clean native mapping on either service and must be escalated before inclusion.

Because the mapping spans two services, `BLEND_MODE_TO_MLT` as specified (`dict[str, str]`) is insufficient. It must extend to carry (service, property_name, value) per mode. This deviation is called out in the escalation triggers below.

## Interface Contracts

### Provides
- `pipelines.compositing.BLEND_MODES: frozenset[str]` -- the 11 canonical abstract names.
- `pipelines.compositing.BLEND_MODE_TO_MLT: dict[str, BlendModeMapping]` -- where `BlendModeMapping` is a `NamedTuple` / `dataclass` with fields `service: str`, `property_name: str`, `value: str`. (Deviation from spec.md's `dict[str, str]` -- see Escalation Triggers below.)
- `pipelines.compositing.apply_composite(project, track_a, track_b, start_frame, end_frame, blend_mode="cairoblend", geometry=None) -> KdenliveProject` -- emits an `AddComposition` intent with `composition_type` set to the service from the mapping and `params` containing `geometry` and the blend-mode property/value pair.

### Requires
None -- no dependencies on other sub-specs. Reuses existing shipped primitives: `AddComposition` intent (`core/models/timeline.py:146`), `patch_project` (`edit_mcp/adapters/kdenlive/patcher.py`), `KdenliveProject` model.

### Shared State
None. Pure function; returns deep-copied project.

## Escalation Triggers (worker MUST honor before coding)

1. **`subtract` has no native MLT composite-transition value.** Options: (a) drop from `BLEND_MODES` entirely, (b) map to `frei0r.cairoblend "difference"` (NOT semantically equivalent), (c) route through a different MLT service (e.g. `frei0r.subtract` filter -- but this is a per-clip effect, not a transition). **STOP and report this to user before implementing.** Until resolved, implement the other 10 modes and mark `subtract` with a sentinel `TODO` comment and a failing test skipped with `pytest.mark.skip(reason="subtract: awaiting MLT mapping decision")`.
2. **`BLEND_MODE_TO_MLT` typing deviation.** Spec says `dict[str, str]`; reality requires `dict[str, NamedTuple(service, property_name, value)]`. Document this deviation at the top of `compositing.py` and in the test file docstring.
3. **Existing `apply_pip` sets `composition_type="composite"` but the base `composite` service has no blend property.** This is outside Sub-Spec 1 scope but note it for Sub-Spec 2: rewiring `apply_pip` through `apply_composite(blend_mode="cairoblend")` will change the emitted `mlt_service` from `"composite"` to `"frei0r.cairoblend"`. This BREAKS byte-identical regression. See Sub-Spec 2's regression handling.

## Implementation Steps

### Step 1: Write failing test file
- **File:** `tests/unit/test_compositing_blend_modes.py`
- **Framework:** pytest (mirrors existing `tests/unit/test_compositing.py`)
- **Tests to write (all initially failing):**
  1. `test_blend_modes_set_exact_membership` -- asserts `BLEND_MODES == frozenset({"cairoblend","screen","lighten","darken","multiply","add","subtract","overlay","destination_in","destination_out","source_over"})`.
  2. `test_blend_mode_to_mlt_has_all_modes` -- every member of `BLEND_MODES` is a key in `BLEND_MODE_TO_MLT` (mark `subtract` with `pytest.skip` until escalation resolved).
  3. `test_blend_mode_mapping_screen` -- `BLEND_MODE_TO_MLT["screen"]` has `service=="frei0r.cairoblend"`, `property_name=="1"`, `value=="screen"`.
  4. `test_blend_mode_mapping_destination_in` -- `service=="qtblend"`, `property_name=="compositing"`, `value=="6"`.
  5. `test_blend_mode_mapping_source_over` -- `service=="qtblend"`, `property_name=="compositing"`, `value=="0"`.
  6. `test_apply_composite_emits_screen` -- calling `apply_composite(project, 1, 2, 0, 120, blend_mode="screen")` results in an opaque `<transition>` element whose `mlt_service` is `frei0r.cairoblend` and whose `<property name="1">` is `screen`. (Use `parse_project` / inspect `project.opaque_elements` post-patch, OR call the patcher manually.)
  7. `test_apply_composite_default_geometry` -- `geometry=None` produces a params entry `geometry` equal to `"0/0:{W}x{H}:100"` using the fixture project's profile width/height.
  8. `test_apply_composite_custom_geometry` -- `geometry="100/50:1920x1080:75"` passes through unchanged in the emitted transition params.
  9. `test_apply_composite_unknown_mode_raises` -- `blend_mode="bogus"` raises `ValueError` whose message contains both `"bogus"` and each of the 11 valid modes.
  10. `test_apply_composite_same_track_raises` -- `track_a == track_b` raises `ValueError` mentioning "same track" or similar.
  11. `test_apply_composite_bad_frames_raises` -- `end_frame <= start_frame` raises `ValueError`.
  12. `test_apply_composite_does_not_mutate_input` -- original project `opaque_elements` length unchanged; returned project has exactly one new opaque element.
- **Run:** `uv run pytest tests/unit/test_compositing_blend_modes.py -v`
- **Expected:** all FAIL with `ImportError` or `AttributeError` (symbols not yet defined).

**Fixture note:** Use the same project-construction helper the existing `tests/unit/test_compositing.py` uses -- inspect that file first. If no helper, build a minimal `KdenliveProject` with a populated `profile` (width=1920, height=1080).

### Step 2: Add `BlendModeMapping` + `BLEND_MODES` + `BLEND_MODE_TO_MLT` to compositing.py
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py`
- **Action:** modify (extend)
- **Changes:**
  - Add at top-of-module (after imports): a `typing.NamedTuple` named `BlendModeMapping` with fields `service: str`, `property_name: str`, `value: str`.
  - Add `BLEND_MODES: frozenset[str]` with exactly the 11 names.
  - Add `BLEND_MODE_TO_MLT: dict[str, BlendModeMapping]` populated per the Stage 3 discovery table (see memory.md). For `subtract`, insert a sentinel mapping or omit + document the escalation.
  - Add a module-level docstring note explaining the service-split and the deviation from spec.md.

### Step 3: Implement `apply_composite`
- **File:** same
- **Action:** add function below existing `apply_wipe`.
- **Signature:** `def apply_composite(project: KdenliveProject, track_a: int, track_b: int, start_frame: int, end_frame: int, blend_mode: str = "cairoblend", geometry: str | None = None) -> KdenliveProject:`
- **Logic (ordered validation):**
  1. If `blend_mode not in BLEND_MODES`: raise `ValueError(f"Unknown blend_mode '{blend_mode}'; valid modes: {sorted(BLEND_MODES)}")`.
  2. If `track_a == track_b`: raise `ValueError("track_a and track_b must be different tracks")`.
  3. If `end_frame <= start_frame`: raise `ValueError(f"end_frame ({end_frame}) must be greater than start_frame ({start_frame})")`.
  4. Look up `mapping = BLEND_MODE_TO_MLT[blend_mode]`.
  5. Compute `geometry` if `None`: `geometry = f"0/0:{project.profile.width}x{project.profile.height}:100"` (follow `apply_pip`'s format at `compositing.py:49`).
  6. Build `params = {"geometry": geometry, mapping.property_name: mapping.value}`.
  7. Create `AddComposition(composition_type=mapping.service, track_a=track_a, track_b=track_b, start_frame=start_frame, end_frame=end_frame, params=params)`.
  8. Return `patch_project(deepcopy(project), [intent])`.
- **Pattern:** follow `apply_pip` at `compositing.py:40-58` for deepcopy + intent + patch flow.

### Step 4: Run tests and confirm pass
- **Run:** `uv run pytest tests/unit/test_compositing_blend_modes.py -v`
- **Expected:** all PASS except the `subtract` test which is `skipped`.

### Step 5: Run full suite for no regressions
- **Run:** `uv run pytest tests/ -v`
- **Expected:** baseline 2513+ tests still pass; new tests add ~11 passing + 1 skipped. `apply_pip` regression not yet affected (that's Sub-Spec 2).

### Step 6: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py tests/unit/test_compositing_blend_modes.py`
- **Message:** `feat: blend mode discovery + apply_composite pipeline`

## Acceptance Criteria

Preserved verbatim from master spec, with type tags:

- `[STRUCTURAL]` Worker inspects `/usr/share/kdenlive/effects/composite.xml` (AND `transitions/composite.xml`, `transitions/qtblend.xml`, `transitions/frei0r_cairoblend.xml`) and records the actual property name carrying blend mode. **Already done in Stage 3; worker re-confirms and documents in module docstring.**
- `[STRUCTURAL]` Module exports `BLEND_MODES: frozenset[str]` with exactly the 11 names.
- `[STRUCTURAL]` Module exports `BLEND_MODE_TO_MLT` mapping each abstract name to its MLT value (extended to carry service + property + value per Stage 3 discovery).
- `[STRUCTURAL]` Module exports `apply_composite(project, track_a, track_b, start_frame, end_frame, blend_mode="cairoblend", geometry=None) -> KdenliveProject`.
- `[BEHAVIORAL]` `apply_composite` with `blend_mode="screen"` emits an `AddComposition` intent whose `params` dict contains the blend-mode key/value pair per the MLT mapping.
- `[BEHAVIORAL]` `apply_composite` with `geometry=None` emits default full-frame geometry `"0/0:WxH:100"` where W,H come from project profile.
- `[BEHAVIORAL]` `apply_composite` with `geometry="100/50:1920x1080:75"` passes geometry through unchanged.
- `[BEHAVIORAL]` `apply_composite` with unknown `blend_mode` raises `ValueError` naming the mode and listing valid ones.
- `[BEHAVIORAL]` `apply_composite` with `track_a == track_b` raises `ValueError`.
- `[BEHAVIORAL]` `apply_composite` with `end_frame <= start_frame` raises `ValueError`.
- `[BEHAVIORAL]` `apply_composite` returns a new `KdenliveProject` (deep copy); original unchanged.
- `[MECHANICAL]` `uv run pytest tests/unit/test_compositing_blend_modes.py -v` passes (with `subtract` test skipped pending escalation).

## Completeness Checklist

### `BLEND_MODES` membership (exact)

| Abstract name     | Required | Service routing              |
|-------------------|----------|------------------------------|
| cairoblend        | required | frei0r.cairoblend / "1" / "normal" |
| screen            | required | frei0r.cairoblend / "1" / "screen" |
| lighten           | required | frei0r.cairoblend / "1" / "lighten" |
| darken            | required | frei0r.cairoblend / "1" / "darken" |
| multiply          | required | frei0r.cairoblend / "1" / "multiply" |
| add               | required | frei0r.cairoblend / "1" / "add" |
| overlay           | required | frei0r.cairoblend / "1" / "overlay" |
| subtract          | required | **ESCALATE** -- no native mapping |
| destination_in    | required | qtblend / "compositing" / "6" |
| destination_out   | required | qtblend / "compositing" / "8" |
| source_over       | required | qtblend / "compositing" / "0" |

### `apply_composite` parameters

| Field        | Type                    | Required | Default       |
|--------------|-------------------------|----------|---------------|
| project      | KdenliveProject         | required | --            |
| track_a      | int                     | required | --            |
| track_b      | int                     | required | --            |
| start_frame  | int                     | required | --            |
| end_frame    | int                     | required | --            |
| blend_mode   | str (must be in BLEND_MODES) | optional | "cairoblend" |
| geometry     | str \| None             | optional | None -> "0/0:WxH:100" |

### Validation invariants
- `blend_mode in BLEND_MODES` -- raises ValueError otherwise (error msg MUST name the bad mode AND list all valid modes).
- `track_a != track_b` -- raises ValueError.
- `end_frame > start_frame` -- raises ValueError.
- Input `project` never mutated (deep copy).

## Verification Commands

- **Build:** `uv sync`
- **Tests (this sub-spec):** `uv run pytest tests/unit/test_compositing_blend_modes.py -v`
- **Tests (regression):** `uv run pytest tests/ -v`
- **Manual XML inspection:** `cat /usr/share/kdenlive/transitions/frei0r_cairoblend.xml /usr/share/kdenlive/transitions/qtblend.xml`

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py:40` (`apply_pip`) -- deepcopy + intent + patch pattern.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py:61` (`apply_wipe`) -- validation-then-intent pattern with `VALID_WIPE_TYPES` set as precedent for `BLEND_MODES`.
- `workshop-video-brain/src/workshop_video_brain/core/models/timeline.py:146` (`AddComposition`) -- intent shape.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:746` (`_apply_add_composition`) -- shows exactly how `composition_type` becomes `mlt_service` and `params` become `<property>` children. Important for asserting emission in tests.
- `tests/unit/test_compositing.py` -- test style, fixture construction for `KdenliveProject`.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` | Modify | Add `BlendModeMapping`, `BLEND_MODES`, `BLEND_MODE_TO_MLT`, `apply_composite`. |
| `tests/unit/test_compositing_blend_modes.py` | Create | Unit tests for all new symbols and `apply_composite` behavior. |
