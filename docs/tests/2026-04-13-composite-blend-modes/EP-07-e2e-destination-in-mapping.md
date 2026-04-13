---
scenario_id: "EP-07"
title: "End-to-end: destination_in writes correct MLT value from mapping"
tool: "bash"
type: test-scenario
sequential: true
covers: ["[BEHAVIORAL] E2E destination_in mapping"]
tags: [test-scenario, mcp, behavioral, e2e, critical]
---

# Scenario EP-07: E2E destination_in mapping

## Description
Parallel to EP-06 but exercises a non-identity mapping (spec's example `destination_in -> dst-in`). Validates the mapping survives the entire parse->apply->serialize->reparse loop.

## Preconditions
- As EP-06.

## Steps
1. Copy fixture into workspace.
2. Call `composite_set(..., blend_mode="destination_in")`.
3. Re-parse the written `.kdenlive`.
4. Locate the new composite transition.
5. Assert the `compositing` property equals `BLEND_MODE_TO_MLT["destination_in"]` exactly (NOT the abstract name).

## Expected Results
- Written MLT value matches the mapping.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_e2e_destination_in -v`

## Pass / Fail Criteria
- **Pass:** MLT value matches mapping.
- **Fail:** Abstract name written, or wrong value.
