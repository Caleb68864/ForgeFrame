---
scenario_id: "SS3-14"
title: "Full suite passes (no regressions)"
tool: "bash"
type: test-scenario
tags: [test-scenario, mechanical, regression, sequential]
---

# Scenario SS3-14: Full suite passes (no regressions)

## Description
Verifies `[MECHANICAL]` requirement 13 + Verification step 1: `uv run pytest tests/ -v` exits 0 with the new tests added on top of the baseline (~2357) and zero regressions in existing suites.

## Preconditions
- All three sub-specs implemented and merged.
- Generated `effect_catalog.py` checked in.

## Steps
1. From repo root run `uv run pytest tests/ -v`.
2. Inspect exit code and final summary line.
3. Confirm no FAILED or ERROR lines.

## Expected Results
- Exit 0.
- Total passing test count >= baseline + new SS1+SS2+SS3 backing tests.

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** Exit 0, no regressions.
- **Fail:** Any failure or error.
