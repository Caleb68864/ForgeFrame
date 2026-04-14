---
scenario_id: "SR-01"
title: "Selection heuristic yields at least 20 wrappable effects"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - heuristic
sequential: false
---

# Scenario SR-01: Selection heuristic yields at least 20 wrappable effects

## Description
Verifies the wrappable-effect selection heuristic in `effect_wrapper_gen.select_wrappable_effects` returns >= 20 effects from the real catalog. This is an escalation trigger in the spec -- fewer than 20 means the heuristic needs tuning.

## Preconditions
- `effect_catalog.CATALOG` contains the full 321 entries.
- `effect_wrapper_gen.py` is importable.

## Steps
1. Import `CATALOG` from `workshop_video_brain.edit_mcp.pipelines.effect_catalog`.
2. Import `select_wrappable_effects` from `workshop_video_brain.edit_mcp.pipelines.effect_wrapper_gen`.
3. Call `effects = select_wrappable_effects(CATALOG)`.
4. Assert `len(effects) >= 20`.
5. Assert every returned `EffectDef` has `category == "video"`, `len(params) <= 8`, `display_name` non-empty, and a `kdenlive_id` matching `^[A-Za-z0-9_-]+$`.

## Expected Results
- Function returns a list with length >= 20.
- Every member satisfies all four heuristic rules.
- No exception raised.

## Execution Tool
bash -- run `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_select_wrappable_effects_yield -v` from repo root.

## Pass / Fail Criteria
- **Pass:** Assertion passes, test green.
- **Fail:** Count < 20 (triggers heuristic tuning escalation) or any entry violates heuristic rules.
