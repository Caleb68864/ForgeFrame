---
scenario_id: "SR-18"
title: "apply_paste invalid mode raises ValueError listing valid modes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
  - error-path
---

# Scenario SR-18: Invalid paste mode

## Description
Verifies `[BEHAVIORAL]` -- calling `apply_paste(... mode="merge")` (or any string outside {append, prepend, replace}) raises `ValueError` whose message lists the three valid modes.

## Preconditions
- Pipeline module importable; valid stack dict available.

## Steps
1. With `pytest.raises(ValueError) as exc`: call `apply_paste(project, (2,0), stack, mode="merge")`.
2. Assert `str(exc.value)` contains all three: "append", "prepend", "replace".
3. Repeat with `mode=""`, `mode=None`, `mode="APPEND"` (case-sensitive expected).

## Expected Results
- All invalid modes raise `ValueError` with valid-modes hint.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_invalid_mode -v`

## Pass / Fail Criteria
- **Pass:** Raises with helpful message every time.
- **Fail:** Silent acceptance, wrong exception, or unhelpful message.
