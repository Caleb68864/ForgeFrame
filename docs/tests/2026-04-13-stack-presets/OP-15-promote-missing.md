---
scenario_id: "OP-15"
title: "promote_to_vault with missing workspace preset raises FileNotFoundError"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-15: promote_to_vault missing source

## Description
Verifies `[BEHAVIORAL]` -- promoting a name that doesn't exist in the workspace tier raises `FileNotFoundError`.

## Preconditions
- Empty `<ws>/stacks/`.

## Steps
1. Call `promote_to_vault("ghost", ws, vault)` inside `pytest.raises(FileNotFoundError)`.
2. Assert message contains `"ghost"` and the workspace path.

## Expected Results
- FileNotFoundError raised; vault file NOT created.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_promote_missing -v`

## Pass / Fail Criteria
- **Pass:** Raise + no vault write.
- **Fail:** Otherwise.
