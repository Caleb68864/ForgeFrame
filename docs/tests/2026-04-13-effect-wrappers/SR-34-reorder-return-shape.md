---
scenario_id: "SR-34"
title: "Reorder return shape matches spec contract"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - contract
sequential: true
---

# Scenario SR-34: Reorder return shape contract

## Steps
1. For each reorder tool, invoke against a 4-filter stack with a valid `effect_index`.
2. Assert return dict has top-level keys `status` and `data`.
3. Assert `data` has keys `effect_index_before`, `effect_index_after`, `snapshot_id`.
4. Assert `snapshot_id` is a non-empty string and exists on disk in the snapshots directory.
5. Assert signature is `(workspace_path, project_file, track, clip, effect_index)` (via `inspect.signature`).

## Expected Results
- Shape and signature match spec exactly across all four tools.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_return_shape -v`

## Pass / Fail Criteria
- **Pass:** shape matches for all four.
- **Fail:** missing key or wrong signature.
