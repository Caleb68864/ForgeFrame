---
scenario_id: "SR-27"
title: "Each write call produces snapshot_id; snapshot dir exists on disk"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - sequential
---

# Scenario SR-27: Auto-snapshot on writes

## Description
Verifies `[BEHAVIORAL]` -- `effects_paste` and `effect_reorder` each return a non-empty `snapshot_id` and a corresponding snapshot artifact exists on disk in the expected workspace snapshot directory. `effects_copy` is a read-only call -- assert it does NOT create a snapshot (or that its envelope omits/empties `snapshot_id` per existing policy).

## Preconditions
- Fresh workspace with fixture.
- Sequential.

## Steps
1. List baseline contents of snapshot directory.
2. Call `effects_copy(...)`; assert no new snapshot directory entry.
3. Call `effects_paste(...)`; capture `sid_paste = result.data.snapshot_id`.
4. Assert snapshot dir contains an entry referencing `sid_paste`.
5. Call `effect_reorder(...)`; capture `sid_reorder`.
6. Assert another snapshot exists for `sid_reorder` and `sid_reorder != sid_paste`.

## Expected Results
- Writes auto-snapshot; reads do not.
- `snapshot_id` strings non-empty and unique per call.
- On-disk snapshot artifacts present.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_snapshot_id -v`

## Pass / Fail Criteria
- **Pass:** Snapshots present and ids match.
- **Fail:** Missing snapshot, missing id, or read created snapshot.
