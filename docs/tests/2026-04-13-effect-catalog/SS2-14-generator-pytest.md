---
scenario_id: "SS2-14"
title: "generator pytest run passes"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, mechanical]
---

# Scenario SS2-14: generator pytest run passes

## Description
Verifies `[MECHANICAL]` `uv run pytest tests/unit/test_effect_catalog_generator.py -v` exits 0.

## Preconditions
- All Sub-Spec 2 implementation merged.

## Steps
1. `uv run pytest tests/unit/test_effect_catalog_generator.py -v`.
2. Inspect exit code.

## Expected Results
- Exit 0; all SS2-* backing tests PASSED.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0.
- **Fail:** Any failure.
