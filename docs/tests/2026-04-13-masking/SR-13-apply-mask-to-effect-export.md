---
scenario_id: "SR-13"
title: "apply_mask_to_effect export signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-2
---

# Scenario SR-13: apply_mask_to_effect export signature and return shape

## Description
Verifies [STRUCTURAL] that `masking` exports `apply_mask_to_effect(project, clip_ref, mask_effect_index, target_effect_index) -> dict` returning `{"reordered": bool, "mask_effect_index": int, "target_effect_index": int}`.

## Preconditions
- Module importable.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines.masking import apply_mask_to_effect`.
2. Inspect `inspect.signature(apply_mask_to_effect)`; assert parameter names in order: `project, clip_ref, mask_effect_index, target_effect_index`.
3. Invoke against a minimal fixture project with a mask already at index 0 and target at index 1; assert return type is `dict` with exactly the three keys and correct Python types.

## Expected Results
- Signature matches.
- Return dict has exactly `reordered` (bool), `mask_effect_index` (int), `target_effect_index` (int).

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_apply_mask_to_effect_export -v`

## Pass / Fail Criteria
- **Pass:** signature and return keys match spec.
- **Fail:** missing parameter, extra keys, or wrong types.
