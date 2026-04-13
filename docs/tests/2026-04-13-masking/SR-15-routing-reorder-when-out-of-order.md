---
scenario_id: "SR-15"
title: "Reorder when mask_idx >= target_idx"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-2
---

# Scenario SR-15: Reorder when mask_idx >= target_idx

## Description
Verifies [BEHAVIORAL] that when `mask_effect_index >= target_effect_index`, `apply_mask_to_effect` reorders via `patcher.reorder_effects` so the mask precedes the target, and returns `reordered=True` with updated indices.

## Preconditions
- Fixture project where the rotoscoping mask filter is at index 1 and a glow filter is at index 0.

## Steps
1. Call `apply_mask_to_effect(project, clip_ref, mask_effect_index=1, target_effect_index=0)`.
2. Capture return.
3. Re-read clip filter stack from the in-memory project (or re-serialize and parse).
4. Assert mask is now at a lower index than the (post-move) target.
5. Also test the equal case: `mask_effect_index == target_effect_index` treated as needing reorder or rejected — confirm behavior by spec intent ("mask precedes target"). (If implementation treats equal as error, assert error; otherwise assert reorder.)

## Expected Results
- `reordered=True`.
- Returned `mask_effect_index < target_effect_index` post-reorder.
- Stack on disk reflects new order (mask first).

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_reorder_when_out_of_order -v`

## Pass / Fail Criteria
- **Pass:** reorder happens and return indices reflect new positions.
- **Fail:** no mutation, or `reordered` flag wrong, or indices stale.
