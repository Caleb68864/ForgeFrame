---
scenario_id: "INT-06"
title: "Invalid effect_index raises MCP error listing effects"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - behavioral
  - edge-case
---

# Scenario INT-06: MCP invalid effect_index error contract

## Description
Verifies [BEHAVIORAL] Sub-Spec 4 -- calling a keyframe tool with an out-of-range `effect_index` raises an MCP-layer error whose message lists available effects on that clip.

## Preconditions
- Fixture with a known small number of effects on clip `(2, 0)`.

## Steps
1. Call `effect_keyframe_set_scalar(workspace, track=2, clip=0, effect_index=99, property="amount", keyframes=[{"frame":0,"value":1.0,"easing":"linear"}])`.
2. Assert the MCP tool raises (or returns an MCP error envelope).
3. Assert the error content contains a listing of available effects (index + mlt_service + kdenlive_id) on clip `(2, 0)`.
4. Repeat for a non-existent clip reference; assert clip-level error envelope.

## Expected Results
- Actionable error at the MCP boundary.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_invalid_effect_index -v`

## Pass / Fail Criteria
- **Pass:** Error surfaces the available-effects listing.
- **Fail:** Opaque error or silent no-op.
