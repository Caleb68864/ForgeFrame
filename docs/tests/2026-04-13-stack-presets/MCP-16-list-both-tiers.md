---
scenario_id: "MCP-16"
title: "effect_stack_list(scope='all') returns presets from both tiers with scope labels"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
sequential: true
---

# Scenario MCP-16: List across tiers via MCP

## Description
Verifies `[BEHAVIORAL]` -- with 2 workspace presets and 3 vault presets, `effect_stack_list(scope="all")` returns 5 entries with correct `scope` labels (matches Verification step 6 in spec).

## Preconditions
- Workspace populated with 2 presets; vault populated with 3 presets.

## Steps
1. Call `effect_stack_list(workspace_path=ws, scope="all")`.
2. Assert `len(data.presets) == 5`.
3. Group by scope: 2 `"workspace"`, 3 `"vault"`.
4. Repeat with `scope="workspace"` -> 2 entries; `scope="vault"` -> 3 entries.
5. If a name appears in both tiers (Edge Case): both appear in `scope="all"`; under `scope="workspace"` lookup workspace wins.

## Expected Results
- Counts and labels per spec.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_list_both_tiers -v`

## Pass / Fail Criteria
- **Pass:** As documented.
- **Fail:** Wrong counts or labels.
