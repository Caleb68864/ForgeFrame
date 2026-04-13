---
scenario_id: "SS3-02"
title: "effect_info return shape matches contract"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, structural]
---

# Scenario SS3-02: effect_info return shape matches contract

## Description
Verifies `[STRUCTURAL]` return shape: `{"status","data":{"kdenlive_id","mlt_service","display_name","description","category","params":[{"name","display_name","type","default","min","max","decimals","values","value_labels","keyframable"}]}}`.

## Preconditions
- Generated CATALOG importable; at least one effect with multiple params (`acompressor`).

## Steps
1. Call `effect_info("acompressor")`.
2. Assert top-level keys: `{"status", "data"}`.
3. Assert `result["status"] == "success"`.
4. Assert data keys: `{"kdenlive_id","mlt_service","display_name","description","category","params"}`.
5. Assert `params` is a list; each item has the 10 documented keys.
6. Assert all values are JSON-serialisable: `json.dumps(result)` succeeds.

## Expected Results
- Shape matches contract; JSON-serialisable.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_shape -v`

## Pass / Fail Criteria
- **Pass:** Keys + serialisability hold.
- **Fail:** Missing key or non-serialisable value.
