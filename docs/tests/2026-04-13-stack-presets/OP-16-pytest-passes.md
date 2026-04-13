---
scenario_id: "OP-16"
title: "tests/unit/test_stack_presets_ops.py passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - mechanical
---

# Scenario OP-16: Ops unit pytest passes

## Description
Verifies `[MECHANICAL]` -- the new ops unit test file passes end-to-end.

## Preconditions
- Sub-Spec 2 implementation complete; all OP-* scenarios implemented as tests.

## Steps
1. Run `uv run pytest tests/unit/test_stack_presets_ops.py -v`.

## Expected Results
- Exit code 0.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py -v`

## Pass / Fail Criteria
- **Pass:** Zero failures/errors.
- **Fail:** Any failure.
