---
scenario_id: "SS3-07"
title: "effect_info by mlt_service returns same entry"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, behavioral]
---

# Scenario SS3-07: effect_info by mlt_service returns same entry

## Description
Verifies `[BEHAVIORAL]` lookup polymorphism: `effect_info("avfilter.acompressor")` returns the same EffectDef as `effect_info("acompressor")`.

## Preconditions
- CATALOG includes `acompressor`.

## Steps
1. `by_id = effect_info("acompressor")`.
2. `by_service = effect_info("avfilter.acompressor")`.
3. Assert both have `status == "success"`.
4. Assert `by_id["data"] == by_service["data"]`.

## Expected Results
- Same data returned by either lookup key.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_by_service -v`

## Pass / Fail Criteria
- **Pass:** Equality holds.
- **Fail:** Different data or error.
