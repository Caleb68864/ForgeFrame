---
scenario_id: "MCP-08"
title: "effect_stack_preset rejects unknown mlt_service with _err naming the service"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
---

# Scenario MCP-08: Catalog validation rejection

## Description
Verifies `[BEHAVIORAL]` -- if the source clip has a filter whose `mlt_service` is not in the catalog, `effect_stack_preset` returns the standard `_err` envelope and names the offending service.

## Preconditions
- Ephemeral fixture copy where one filter's `<property name="mlt_service">` is hand-mutated to `nonexistent.service` before the call.

## Steps
1. Inject the bad service into the fixture clip's filter via direct XML edit.
2. Call `effect_stack_preset(...)`.
3. Assert response `status == "error"` (or matches the project's `_err` convention).
4. Assert error message contains `"nonexistent.service"`.
5. Assert NO file was written to `<ws>/stacks/`.

## Expected Results
- _err with bad service name; nothing persisted.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_preset_bad_service_rejected -v`

## Pass / Fail Criteria
- **Pass:** Error envelope + service named + no file.
- **Fail:** Otherwise.
