---
title: "Effect Wrappers + Presets for Kdenlive MCP Test Plan"
project: "Workshop Video Brain"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - effect-wrappers
---

# Test Plan: Effect Wrappers + Presets for Kdenlive MCP

## Meta
- Project: Workshop Video Brain (ForgeFrame)
- Date: 2026-04-13
- Author: Forge (non-interactive)
- Spec Source: `docs/specs/2026-04-13-effect-wrappers.md`
- Scope: All three sub-specs (generator, presets, reorder)
- Test Framework: pytest (via `uv run pytest`)
- Tool Hint: bash
- Holdout Mode: none (all scenarios visible)

## Prerequisites
- Python 3.12+ with `uv` installed
- Working copy of ForgeFrame repo at `/home/caleb/Projects/ForgeFrame`
- Specs 1-6 shipped; `effect_catalog.CATALOG` loaded with 321 entries
- Test fixtures: a workspace with a project containing at least one track with a clip and a 4-filter effect stack
- Snapshots directory writable
- Tests self-contained: each scenario builds its own workspace/project via pytest fixtures; scenarios marked `sequential: true` mutate shared state

## Scenarios

| ID | Title | Area | Priority | Sequential |
|----|-------|------|----------|------------|
| SR-01 | Selection heuristic yields at least 20 wrappable effects | Generator | High | No |
| SR-02 | `render_wrapper_module` produces valid Python for `transform` | Generator | High | No |
| SR-03 | `emit_wrappers_package` is idempotent (byte-identical re-runs) | Generator | High | No |
| SR-04 | Generated wrappers package imports cleanly (smoke test) | Generator | High | No |
| SR-05 | Keyframe-capable param types add `keyframes: str = ""` kwarg | Generator | Medium | No |
| SR-06 | Effects with >8 params are skipped by heuristic | Generator | Medium | No |
| SR-07 | CLI `catalog regenerate-wrappers --output` writes package | Generator | Medium | No |
| SR-08 | Script `scripts/generate_effect_wrappers.py` equivalent to CLI | Generator | Medium | No |
| SR-09 | Generator refuses to overwrite hand-written files without `--force` | Generator | Medium | No |
| SR-10 | Wrapper name collision detection errors before writing | Generator | Medium | No |
| SR-11 | `tools_helpers` exports helpers consumed by `tools.py` (DRY) | Generator | Medium | No |
| SR-12 | Generated `__init__.py` exposes all wrapped tool names | Generator | Medium | No |
| SR-13 | `effect_glitch_stack` inserts 5 filters in specified order with single snapshot | Presets | High | Yes |
| SR-14 | `effect_glitch_stack` scales params with intensity (0.0 vs 1.0) | Presets | High | Yes |
| SR-15 | `effect_glitch_stack` errors when frei0r service missing from catalog | Presets | Medium | No |
| SR-16 | `effect_fade` writes opacity keyframes on transform `rect` | Presets | High | Yes |
| SR-17 | `effect_fade` respects easing (MLT operator char per keyframe) | Presets | High | Yes |
| SR-18 | `effect_fade` errors when both fade_in and fade_out are zero | Presets | Medium | No |
| SR-19 | `effect_fade` clamps when fade_in + fade_out > clip duration | Presets | Medium | Yes |
| SR-20 | `flash_cut_montage` splits clip and applies effect chain | Presets | High | Yes |
| SR-21 | `flash_cut_montage` errors on n_cuts < 2 | Presets | Medium | No |
| SR-22 | `flash_cut_montage` errors when n_cuts > clip duration frames | Presets | Medium | No |
| SR-23 | Presets take single snapshot at start, not per-filter | Presets | Medium | Yes |
| SR-24 | `move_to_top` happy path moves filter 3 to index 0 | Reorder | High | Yes |
| SR-25 | `move_to_bottom` happy path moves filter 0 to last index | Reorder | High | Yes |
| SR-26 | `move_up` happy path decrements index by 1 | Reorder | High | Yes |
| SR-27 | `move_down` happy path increments index by 1 | Reorder | High | Yes |
| SR-28 | `move_up` at index 0 is no-op with "already at top" note | Reorder | High | No |
| SR-29 | `move_down` at last index is no-op with "already at bottom" note | Reorder | High | No |
| SR-30 | `move_to_top` at index 0 is no-op | Reorder | Medium | No |
| SR-31 | `move_to_bottom` at last index is no-op | Reorder | Medium | No |
| SR-32 | Reorder out-of-range effect_index returns `_err` with stack length | Reorder | High | No |
| SR-33 | Reorder on single-filter stack — all four are no-ops | Reorder | Medium | No |
| SR-34 | Reorder return shape matches spec contract | Reorder | Medium | Yes |
| SR-35 | Full suite regression (`uv run pytest tests/ -v`) passes | Integration | High | Yes |

## Coverage Summary
- Total scenarios: 35
- Generator (Sub-Spec 1) scenarios: 12
- Presets (Sub-Spec 2) scenarios: 11
- Reorder (Sub-Spec 3) scenarios: 11
- Full-suite regression: 1
- Sequential scenarios: 13 (mutate workspace project files or share fixture state)
- Spec requirement coverage: All acceptance criteria across the three sub-specs mapped to at least one scenario

## Priority Order
1. Generator core: selection heuristic, module render, idempotency, import smoke (SR-01..SR-04)
2. Preset behavioral correctness: glitch param scaling, fade keyframes + easing, montage split+chain (SR-13, SR-14, SR-16, SR-17, SR-20)
3. Reorder happy + no-op + out-of-range (SR-24..SR-29, SR-32)
4. Remaining structural/edge scenarios
5. Full-suite regression last (SR-35)

## Execution
Run the plan with:
```
/forge-test-run docs/tests/2026-04-13-effect-wrappers/test-plan.md
```

Each scenario file lists the exact `uv run pytest` invocation to execute it in isolation.
