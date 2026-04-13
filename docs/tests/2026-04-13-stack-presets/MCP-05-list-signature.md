---
scenario_id: "MCP-05"
title: "effect_stack_list signature and return envelope"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario MCP-05: effect_stack_list envelope shape

## Description
Verifies `[STRUCTURAL]` -- `effect_stack_list(workspace_path, scope: str = "all")` returns `{"status","data":{"presets":[...],"skipped":[...]}}`.

## Preconditions
- Workspace + vault populated with at least one preset each (and one malformed file).

## Steps
1. Inspect signature; assert default `scope="all"`.
2. Call. Assert `data.presets` is a list and `data.skipped` is a list.
3. Each entry in `presets` has `name`, `scope`, `tags`, `effect_count`, `description`, `path`.

## Expected Results
- Envelope matches.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_list_envelope -v`

## Pass / Fail Criteria
- **Pass:** Match.
- **Fail:** Otherwise.
