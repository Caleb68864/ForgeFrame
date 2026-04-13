---
scenario_id: "SS3-13"
title: "MCP+CLI pytest module passes"
tool: "bash"
type: test-scenario
tags: [test-scenario, mechanical]
---

# Scenario SS3-13: MCP+CLI pytest module passes

## Description
Verifies `[MECHANICAL]` `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py tests/unit/test_cli_catalog.py -v` exits 0.

## Preconditions
- All Sub-Spec 3 implementation merged.
- Generated catalog importable.

## Steps
1. Run the pytest command above.
2. Inspect exit code.

## Expected Results
- Exit 0; all SS3-* backing tests PASSED.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py tests/unit/test_cli_catalog.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0.
- **Fail:** Any failure.
