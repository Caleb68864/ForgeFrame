---
scenario_id: "EDGE-04"
title: "Auto-snapshot policy not bypassed by keyframe tools"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - edge-case
  - sequential
---

# Scenario EDGE-04: Auto-snapshot not bypassed

## Description
Verifies the "Must Nots: must NOT bypass the existing auto-snapshot policy" constraint -- the four new tools go through the same snapshot hook as existing MCP tools, and calling a tool with a no-op keyframe write still creates a snapshot (or consistently follows existing policy for no-ops).

Complements INT-07 which verifies the id is returned; this scenario verifies the POLICY wiring.

## Preconditions
- Existing auto-snapshot hook identifiable in the MCP call pipeline.
- Fresh workspace copy.

## Steps
1. Patch/spy the auto-snapshot hook used by existing tools (e.g., `effect_add`).
2. Invoke each of the four new tools (scalar/rect/color + effect_find).
3. Assert the snapshot hook fires for the three keyframe-writing tools.
4. Document whether `effect_find` (read-only) triggers a snapshot -- likely no; assert per the implemented policy consistent with other read-only tools.
5. Assert the hook was called with the same signature/context shape as existing tools (no bypass path).

## Expected Results
- Keyframe write tools trigger the standard snapshot hook.
- `effect_find` follows the same read-vs-write policy as other read-only tools (consistent with existing `effect_list_common`).

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_snapshot_policy -v`

## Pass / Fail Criteria
- **Pass:** Hook fires correctly; no custom bypass path.
- **Fail:** Hook skipped, different code path, or inconsistent with existing tools.
