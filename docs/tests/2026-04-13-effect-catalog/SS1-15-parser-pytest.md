---
scenario_id: "SS1-15"
title: "parser pytest run passes"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, mechanical]
---

# Scenario SS1-15: parser pytest run passes

## Description
Verifies `[MECHANICAL]` criterion: `uv run pytest tests/unit/test_effect_catalog_parser.py -v` exits 0 with all SS1-* tests passing.

## Preconditions
- Sub-Spec 1 implementation merged.
- Fixtures present.

## Steps
1. From repo root, run `uv run pytest tests/unit/test_effect_catalog_parser.py -v`.
2. Inspect exit code.

## Expected Results
- Exit code 0.
- All SS1-01 through SS1-14 backing tests reported as PASSED.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0, no failures.
- **Fail:** Any failure or error.
