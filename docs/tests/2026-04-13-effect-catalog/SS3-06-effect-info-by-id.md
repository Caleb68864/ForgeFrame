---
scenario_id: "SS3-06"
title: "effect_info(\"acompressor\") returns full schema"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, behavioral]
---

# Scenario SS3-06: effect_info("acompressor") returns full schema

## Description
Verifies `[BEHAVIORAL]` lookup by `kdenlive_id` returns the catalog entry with full param schema.

## Preconditions
- Generated CATALOG includes `acompressor` (real Kdenlive run).

## Steps
1. `result = effect_info("acompressor")`.
2. Assert `result["status"] == "success"`.
3. Assert `result["data"]["kdenlive_id"] == "acompressor"`.
4. Assert `result["data"]["mlt_service"] == "avfilter.acompressor"`.
5. Assert `len(result["data"]["params"]) == 11`.
6. Assert `result["data"]["params"][0]["name"] == "av.level_in"`.

## Expected Results
- Full schema returned.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_by_id -v`

## Pass / Fail Criteria
- **Pass:** All asserts hold.
- **Fail:** Wrong data or status.
