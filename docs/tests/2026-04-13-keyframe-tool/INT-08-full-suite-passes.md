---
scenario_id: "INT-08"
title: "Full pytest suite passes with no regressions"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - mechanical
  - sequential
---

# Scenario INT-08: Full test suite green

## Description
Verifies [MECHANICAL] criteria across ALL four sub-specs -- the complete project test suite passes and no existing test regresses.

## Preconditions
- All four sub-specs implemented.

## Steps
1. Run `uv run pytest tests/ -v` from repo root.
2. Observe exit code.
3. Observe that the new test modules (`test_patcher_effect_properties.py`, `test_keyframes_pipeline.py`, `test_effect_find.py`, `test_workspace_keyframe_defaults.py`, `test_keyframe_mcp_tools.py`) all execute and pass.
4. Compare pre-implementation baseline suite count to post-implementation suite count; no pre-existing tests should be removed or marked xfail.

## Expected Results
- Exit code `0`.
- All new tests collected and passing.
- No pre-existing tests regressed.

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** Clean green suite.
- **Fail:** Any failure, error, or regression.
