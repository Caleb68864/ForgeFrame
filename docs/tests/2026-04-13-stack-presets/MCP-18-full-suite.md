---
scenario_id: "MCP-18"
title: "Full suite uv run pytest tests/ -v passes with no regressions"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - mechanical
  - regression
---

# Scenario MCP-18: Full pytest suite, no regressions

## Description
Verifies `[MECHANICAL]` -- entire repo test suite (baseline 2407 + new tests added by this spec) passes with no regressions in Spec 1/2/3 or other existing modules.

## Preconditions
- Complete implementation of all three sub-specs.

## Steps
1. Run `uv run pytest tests/ -v` from repo root.
2. Note total pass count >= 2407 + (count of new tests added).

## Expected Results
- Exit code 0; no previously passing tests now fail.

## Execution Tool
bash -- `uv run pytest tests/ -v`

## Pass / Fail Criteria
- **Pass:** Exit code 0.
- **Fail:** Any pre-existing test now fails, or any new test fails.
