---
scenario_id: "INT-05"
title: "effect_find MCP tool returns correct index for fixture"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - behavioral
---

# Scenario INT-05: effect_find MCP end-to-end

## Description
Verifies [BEHAVIORAL] Sub-Spec 4 -- `effect_find(workspace, track=2, clip=0, name="transform")` returns `0` against the fixture.

## Preconditions
- Fixture workspace with `transform` filter at clip `(2, 0)`, effect index `0`.

## Steps
1. Invoke `effect_find` via the MCP layer with `(workspace, 2, 0, "transform")`.
2. Assert return value is `0` (an `int`, not dict).

## Expected Results
- `0` returned.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_effect_find_fixture -v`

## Pass / Fail Criteria
- **Pass:** Exact integer `0`.
- **Fail:** Wrong value, wrong type, or raised error.
