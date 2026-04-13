---
scenario_id: "MCP-11"
title: "effect_stack_apply name not found in either tier returns _err listing both paths"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
---

# Scenario MCP-11: Apply unknown preset name

## Description
Verifies `[BEHAVIORAL]` -- when the named preset is missing from both tiers, `effect_stack_apply` returns `_err` whose message lists both searched paths.

## Preconditions
- Empty workspace and vault preset directories.

## Steps
1. Call `effect_stack_apply(..., name="ghost", mode="")`.
2. Assert `status == "error"`.
3. Assert error message contains both `<ws>/stacks/ghost.yaml` and `<vault>/patterns/effect-stacks/ghost.md`.
4. Assert project file is unchanged on disk (no snapshot created).

## Expected Results
- _err with both paths; no project mutation.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_apply_name_not_found -v`

## Pass / Fail Criteria
- **Pass:** As documented.
- **Fail:** Otherwise.
