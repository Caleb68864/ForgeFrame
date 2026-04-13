---
scenario_id: "SS3-10"
title: "effect_list_common returns >300 catalog-backed entries"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, behavioral, requires-kdenlive]
---

# Scenario SS3-10: effect_list_common returns >300 catalog-backed entries

## Description
Verifies `[BEHAVIORAL]` requirement: `effect_list_common()` is now sourced from the catalog (not the old hardcoded 8) and returns summary entries `{kdenlive_id, mlt_service, display_name, category, short_description}` for every catalog entry.

## Preconditions
- Generated CATALOG with > 300 entries.

## Steps
1. `result = effect_list_common()`.
2. Assert `result["status"] == "success"`.
3. Assert `len(result["data"]["effects"]) > 300`.
4. Pick `entry = result["data"]["effects"][0]`; assert keys = `{"kdenlive_id","mlt_service","display_name","category","short_description"}`.
5. Assert `len(result["data"]["effects"]) == len(CATALOG)` (sourced from catalog).

## Expected Results
- Catalog-backed list with 300+ entries; correct entry shape.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_list_common_count -v`

## Pass / Fail Criteria
- **Pass:** Count + shape match.
- **Fail:** Old 8-entry list or wrong shape.
