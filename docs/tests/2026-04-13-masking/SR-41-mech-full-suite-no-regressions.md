---
scenario_id: "SR-41"
title: "uv run pytest tests/ -v full suite passes with zero regressions"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mechanical
  - sub-spec-3
---

# Scenario SR-41: uv run pytest tests/ -v full suite passes with zero regressions

## Description
Verifies [MECHANICAL] Requirement 12 and Sub-Spec 3 final gate: the complete test suite passes, with no regressions from Specs 1-4 introduced by the masking work.

## Preconditions
- All other scenarios have been attempted.
- No flaky-test skips introduced to hide regressions.

## Steps
1. Run `uv run pytest tests/ -v` from repo root.
2. Capture exit code and summary line.
3. Compare pre-existing test counts (from `git stash` baseline or recorded count) to post-masking counts — expect only additions.

## Expected Results
- Exit code `0`.
- All tests pass.
- No previously-passing test now fails or is skipped.

## Execution Tool
bash — run the command above; if failure occurs, run `uv run pytest tests/ -v --tb=short` and report which tests regressed.

## Pass / Fail Criteria
- **Pass:** exit 0, no regressions.
- **Fail:** any failing test, especially any test that was passing prior to this spec.
