---
scenario_id: "MCP-13"
title: "Snapshot IDs only on apply (preset and promote do not snapshot)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
sequential: true
---

# Scenario MCP-13: Snapshot policy

## Description
Verifies `[BEHAVIORAL]` -- only `effect_stack_apply` mutates the project, so only it produces a `snapshot_id`. `effect_stack_preset` and `effect_stack_promote` write OUTSIDE the project (workspace yaml / vault md) and must not snapshot the project.

## Preconditions
- Fresh ephemeral workspace + fixture copy.
- Snapshot baseline: `len(snapshot_list(project)) == N`.

## Steps
1. Call `effect_stack_preset(..., name="p")`. Assert response `data` does NOT contain `snapshot_id`. Assert `len(snapshot_list(project)) == N` (no new snapshot).
2. Call `effect_stack_apply(..., name="p")`. Assert response `data.snapshot_id` is a non-empty string. Assert the corresponding snapshot directory/file exists on disk. Assert `len(snapshot_list(project)) == N+1`.
3. Call `effect_stack_promote(..., name="p")`. Assert response `data` does NOT contain `snapshot_id`. Assert `len(snapshot_list(project)) == N+1` (still only one new snapshot from the apply).

## Expected Results
- Apply snapshots; preset and promote do not.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_snapshot_policy -v`

## Pass / Fail Criteria
- **Pass:** Counts and presence match.
- **Fail:** Any non-apply tool produces a snapshot, or apply doesn't.
