---
scenario_id: "SR-11"
title: "tools_helpers exports helpers consumed by tools.py (DRY)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - refactor
sequential: false
---

# Scenario SR-11: `tools_helpers.py` exports helpers

## Steps
1. Import `tools_helpers`.
2. Assert it has attributes `_require_workspace`, `_ok`, `_err`, `register_effect_wrapper`.
3. Grep `server/tools.py` for local definitions of `_require_workspace`, `_ok`, `_err` -- none should remain (must import from `tools_helpers`).
4. Run existing `tools.py`-consuming tests -- no behavior change.

## Expected Results
- Helpers live in `tools_helpers`, imported by `tools.py`.
- Existing tests still green.

## Execution Tool
bash -- `uv run pytest tests/unit/test_tools_helpers.py -v`

## Pass / Fail Criteria
- **Pass:** exports present, no duplicate definitions remain.
- **Fail:** any redefinition in `tools.py` or missing helper.
