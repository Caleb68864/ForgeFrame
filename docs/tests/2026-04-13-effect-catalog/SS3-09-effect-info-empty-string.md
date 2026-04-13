---
scenario_id: "SS3-09"
title: "effect_info on empty string returns structured error"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, edge-case]
---

# Scenario SS3-09: effect_info on empty string returns structured error

## Description
Verifies edge-case (spec Edge Cases): empty-string name returns `_err("Effect name cannot be empty.")`.

## Preconditions
- effect_info importable.

## Steps
1. `result = effect_info("")`.
2. Assert `result["status"] == "error"`.
3. Assert `"empty" in result["message"].lower()`.

## Expected Results
- Empty-string explicitly rejected.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_empty_string -v`

## Pass / Fail Criteria
- **Pass:** Error message references emptiness.
- **Fail:** Crash or generic not-found message.
