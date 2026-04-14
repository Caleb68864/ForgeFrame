---
scenario_id: "SR-35"
title: "Full suite regression"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - regression
sequential: true
---

# Scenario SR-35: Full suite regression (`uv run pytest tests/ -v`)

## Description
Acceptance Criterion: full-suite regression (baseline 2552 + new tests) must pass with no regressions.

## Steps
1. From repo root, run `uv run pytest tests/ -v`.
2. Capture exit code and summary line.
3. Assert exit code 0.
4. Assert summary shows no failures or errors.
5. Assert collected test count >= 2552 + new-tests-added.

## Expected Results
- All tests green.
- No regressions in previously-passing tests.

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** exit 0, 0 failures.
- **Fail:** any failure or error anywhere in the suite.
