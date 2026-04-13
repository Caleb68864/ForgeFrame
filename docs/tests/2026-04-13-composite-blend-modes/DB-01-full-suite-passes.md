---
scenario_id: "DB-01"
title: "Full test suite passes (uv run pytest tests/ -v)"
tool: "bash"
type: test-scenario
sequential: true
covers: ["[MECHANICAL] zero-regression full suite"]
tags: [test-scenario, mechanical, meta, critical]
---

# Scenario DB-01: Full suite green

## Description
Spec Requirement 12 + Sub-Spec 2 MECHANICAL: `uv run pytest tests/ -v` passes with no regressions against baseline (spec mentions baseline of 2513 tests + new ones from this spec).

## Preconditions
- All other scenarios' pytest functions committed.
- Fresh `uv sync`.

## Steps
1. Run `uv run pytest tests/ -v` from repo root.
2. Capture exit code and summary line.

## Expected Results
- Exit code 0.
- Summary shows 0 failures, 0 errors.
- Total collected count >= baseline (2513) + newly added tests (Sub-Spec 1 + Sub-Spec 2 files).

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** Exit 0, no failures/errors, collected count meets or exceeds baseline + new.
- **Fail:** Any failure, error, or collection regression.
