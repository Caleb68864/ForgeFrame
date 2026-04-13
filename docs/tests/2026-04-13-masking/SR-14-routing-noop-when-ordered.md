---
scenario_id: "SR-14"
title: "No-op when mask already precedes target"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-2
---

# Scenario SR-14: No-op when mask already precedes target

## Description
Verifies [BEHAVIORAL] that when `mask_effect_index < target_effect_index`, `apply_mask_to_effect` performs no reorder and returns `reordered=False` with indices unchanged.

## Preconditions
- Fixture project with rotoscoping filter at index 0 and a glow filter at index 1 on the target clip.

## Steps
1. Snapshot the current order of filter elements in the clip's MLT XML.
2. Call `apply_mask_to_effect(project, clip_ref, mask_effect_index=0, target_effect_index=1)`.
3. Capture return.
4. Re-read the clip's filter order and compare to the pre-call snapshot.

## Expected Results
- Return: `{"reordered": False, "mask_effect_index": 0, "target_effect_index": 1}`.
- Filter order on disk is byte-identical to the snapshot (no reorder occurred).
- `patcher.reorder_effects` was not invoked (can be asserted by count of mutation calls or byte-equality).

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_noop_when_already_ordered -v`

## Pass / Fail Criteria
- **Pass:** `reordered=False` and no XML change.
- **Fail:** any XML mutation or `reordered=True`.
