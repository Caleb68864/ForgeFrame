---
scenario_id: "SR-30"
title: "mask_apply reorders when mask index > target index and returns reordered=true"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-30: mask_apply reorders when mask index > target index and returns reordered=true

## Description
Verifies [BEHAVIORAL] that `mask_apply` with `mask_effect_index > target_effect_index` triggers a reorder and the return includes `reordered=true` with updated indices.

## Preconditions
- Project fixture with glow at index 0 and rotoscoping mask at index 1 on the target clip.

## Steps
1. Call `mask_apply(..., mask_effect_index=1, target_effect_index=0)`.
2. Assert return `reordered == True`.
3. Re-parse project from disk.
4. Assert mask filter now appears before the glow filter in the clip's filter list.

## Expected Results
- `reordered=true` in return.
- Stack order on disk: mask precedes glow.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_mask_apply_reorders -v`

## Pass / Fail Criteria
- **Pass:** flag and disk state both confirm reorder.
- **Fail:** flag wrong or stack not reordered.
