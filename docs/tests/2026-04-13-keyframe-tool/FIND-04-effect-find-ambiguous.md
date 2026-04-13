---
scenario_id: "FIND-04"
title: "effect_find raises ValueError on ambiguous match"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - effect-find
  - behavioral
  - edge-case
---

# Scenario FIND-04: effect_find ambiguous match

## Description
Verifies [BEHAVIORAL] Sub-Spec 3 edge case -- two filters sharing the same `kdenlive_id` on one clip cause `find` to raise `ValueError` with all matching indices listed.

## Preconditions
- Clip `(2, 0)` has two filters BOTH with `kdenlive_id="transform"` at indices `0` and `2`.

## Steps
1. Call `find(project, (2, 0), "transform")`.
2. Assert `ValueError` raised.
3. Assert the message lists both matching indices (e.g., `[0, 2]`).
4. Assert message guides caller to use `effect_index` directly.

## Expected Results
- Ambiguity surfaces loudly with both indices.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_find.py::test_find_ambiguous -v`

## Pass / Fail Criteria
- **Pass:** ValueError with both indices + guidance.
- **Fail:** Silent first-wins, wrong exception type, or missing indices.
