---
scenario_id: "SR-20"
title: "Stack-ops pipeline unit test file passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - mechanical
---

# Scenario SR-20: tests/unit/test_stack_ops_pipeline.py passes

## Description
Verifies `[MECHANICAL]` gate from Sub-Spec 2.

## Preconditions
- Sub-Spec 2 merged with `tests/unit/test_stack_ops_pipeline.py`.

## Steps
1. Run `uv run pytest tests/unit/test_stack_ops_pipeline.py -v`.

## Expected Results
- Exit 0; all tests PASSED.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0.
- **Fail:** Any failure or non-zero exit.
