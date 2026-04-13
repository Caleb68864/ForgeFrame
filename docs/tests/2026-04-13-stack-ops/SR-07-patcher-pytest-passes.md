---
scenario_id: "SR-07"
title: "Patcher stack-ops unit test file passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - mechanical
---

# Scenario SR-07: tests/unit/test_patcher_stack_ops.py passes

## Description
Verifies `[MECHANICAL]` gate from Sub-Spec 1: the new patcher unit test file runs green.

## Preconditions
- Sub-Spec 1 merged including `tests/unit/test_patcher_stack_ops.py`.

## Steps
1. From repo root: `uv run pytest tests/unit/test_patcher_stack_ops.py -v`.
2. Capture exit code.

## Expected Results
- Exit code 0.
- All collected tests reported as PASSED.
- No skips for the core SR-01..SR-06 cases.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0, no failures.
- **Fail:** Any failed test or non-zero exit.
