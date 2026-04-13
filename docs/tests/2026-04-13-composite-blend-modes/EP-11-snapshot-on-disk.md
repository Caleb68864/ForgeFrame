---
scenario_id: "EP-11"
title: "composite_set creates snapshot on disk"
tool: "bash"
type: test-scenario
sequential: true
covers: ["[BEHAVIORAL] snapshot verification"]
tags: [test-scenario, mcp, behavioral]
---

# Scenario EP-11: Snapshot on disk after composite_set

## Description
Spec Sub-Spec 2 BEHAVIORAL: "`composite_set` snapshot_id exists on disk after call." This validates the auto-snapshot (mirroring `composite_pip` / `composite_wipe` pattern with `create_snapshot(..., description="before_composite_<mode>")`).

## Preconditions
- Workspace set up.

## Steps
1. Capture list of snapshot files/IDs before the call (e.g. via `snapshot_list` tool or file listing of the snapshot directory).
2. Call `composite_set(..., blend_mode="screen")`.
3. Capture snapshot list after.
4. Assert the returned `snapshot_id` matches a newly created entry.
5. Assert the snapshot file exists on disk (check via filesystem).
6. Assert `snapshot_restore(snapshot_id)` yields a project file byte-identical to the pre-call fixture copy.

## Expected Results
- New snapshot created; `snapshot_id` maps to a real artifact; restore yields pre-call state.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_snapshot_created -v`

## Pass / Fail Criteria
- **Pass:** Snapshot present and restorable.
- **Fail:** No snapshot, missing file, or restore mismatch.
