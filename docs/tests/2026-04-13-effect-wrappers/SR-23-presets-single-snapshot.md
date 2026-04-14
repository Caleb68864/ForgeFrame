---
scenario_id: "SR-23"
title: "Presets take single snapshot at start, not per-filter"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - snapshot
sequential: true
---

# Scenario SR-23: Presets create exactly one snapshot per call

## Steps
1. For each preset (`effect_glitch_stack`, `effect_fade`, `flash_cut_montage`):
   a. Snapshot count before = N.
   b. Invoke preset.
   c. Assert snapshot count after = N + 1.
2. Assert returned `snapshot_id` appears in `snapshot_list`.

## Expected Results
- Exactly one new snapshot per preset invocation.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_single_snapshot_per_preset -v`

## Pass / Fail Criteria
- **Pass:** N+1 after each.
- **Fail:** N+K (K>1), i.e., per-filter snapshotting.
