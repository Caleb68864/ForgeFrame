---
scenario_id: "IO-14"
title: "tests/unit/test_stack_presets_io.py passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - mechanical
---

# Scenario IO-14: I/O unit pytest passes

## Description
Verifies `[MECHANICAL]` -- the new I/O unit test file passes end-to-end.

## Preconditions
- All Sub-Spec 1 implementation in place; all IO-* scenarios above implemented as tests.

## Steps
1. Run `uv run pytest tests/unit/test_stack_presets_io.py -v` from repo root.

## Expected Results
- Exit code 0; all tests pass.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py -v`

## Pass / Fail Criteria
- **Pass:** Zero failures, zero errors.
- **Fail:** Any failure or collection error.
