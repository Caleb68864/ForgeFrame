---
scenario_id: "SR-34"
title: "Every write-mutating MCP call returns a snapshot_id that exists on disk"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-34: Every write-mutating MCP call returns a snapshot_id that exists on disk

## Description
Verifies [BEHAVIORAL] Requirement 11: all write-mutating tools (`mask_set`, `mask_set_shape`, `mask_apply`, `effect_chroma_key`, `effect_chroma_key_advanced`, `effect_object_mask`) auto-snapshot and return a `snapshot_id` locatable on disk.

## Preconditions
- Fresh workspace + project fixture.
- Snapshot directory convention known (reuse from Spec 1).

## Steps
1. Call `mask_set_shape(..., shape="rect", bounds="[0,0,1,1]")` → collect `snapshot_id_1`.
2. Call `effect_chroma_key(..., color="#00FF00")` → `snapshot_id_2`.
3. Call `effect_chroma_key_advanced(..., color="#00FF00", tolerance_near=0.1, tolerance_far=0.3)` → `snapshot_id_3`.
4. Call `effect_object_mask(...)` → `snapshot_id_4`.
5. Call `mask_apply(..., mask_effect_index=0, target_effect_index=1)` → `snapshot_id_5`.
6. Call `mask_set(..., type="rotoscoping", params='{"points":[[0,0],[1,0],[1,1]]}')` → `snapshot_id_6`.
7. For each snapshot_id, Glob or stat-check the snapshot directory and assert a file/dir named for that id exists.
8. Assert all six IDs are distinct.

## Expected Results
- All six snapshot IDs resolve to on-disk artifacts.
- All six IDs are unique.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_snapshot_ids_persist -v`

## Pass / Fail Criteria
- **Pass:** all 6 IDs present on disk, distinct.
- **Fail:** any missing, duplicated, or absent from disk.
