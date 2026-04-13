---
scenario_id: "SS3-08"
title: "effect_info on missing name returns structured error"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, behavioral, error-path]
---

# Scenario SS3-08: effect_info on missing name returns structured error

## Description
Verifies `[BEHAVIORAL]` not-found path: returns `{"status":"error","message":"Effect not found: nonexistent_effect. Try \`effect_list_common\` for the registry."}`.

## Preconditions
- CATALOG does not contain `nonexistent_effect`.

## Steps
1. `result = effect_info("nonexistent_effect")`.
2. Assert `result["status"] == "error"`.
3. Assert `result["message"]` matches expected exact string (or contains both `"nonexistent_effect"` and `"effect_list_common"`).
4. Assert no exception raised.

## Expected Results
- Structured error, no raise.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_not_found -v`

## Pass / Fail Criteria
- **Pass:** Error structure matches.
- **Fail:** Raise or wrong message.
