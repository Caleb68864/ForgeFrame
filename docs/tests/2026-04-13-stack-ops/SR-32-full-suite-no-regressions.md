---
scenario_id: "SR-32"
title: "Full suite uv run pytest tests/ -v passes (no regressions)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - regression
  - mechanical
---

# Scenario SR-32: Full suite regression gate

## Description
Verifies `[MECHANICAL]` overall gate -- the entire test suite passes after Sub-Specs 1-3 are merged, ensuring no regressions to Spec 1 keyframes, serializer, or any other shipped functionality.

## Preconditions
- Sub-Specs 1, 2, 3 merged.

## Steps
1. From repo root: `uv run pytest tests/ -v`.
2. Capture pass/fail summary.

## Expected Results
- Exit 0.
- All previously-passing tests still pass.
- New tests for SR-01..SR-31 all pass.

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** Exit 0, no failures.
- **Fail:** Any test failure (regression or new) or non-zero exit.
