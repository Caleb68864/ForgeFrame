---
scenario_id: "FIND-03"
title: "effect_find raises LookupError listing available effects on no match"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - effect-find
  - behavioral
  - edge-case
---

# Scenario FIND-03: effect_find no-match error

## Description
Verifies [BEHAVIORAL] Sub-Spec 3 -- when no filter matches by `kdenlive_id` or `mlt_service`, `LookupError` is raised and the message lists all effects on the clip.

## Preconditions
- Clip `(2, 0)` has two filters, neither matching the requested name.

## Steps
1. Call `find(project, (2, 0), "nonexistent_filter")`.
2. Assert `LookupError` raised.
3. Assert the exception message includes each filter's `(index, mlt_service, kdenlive_id)` triple so the caller can disambiguate.

## Expected Results
- Actionable error listing available effects.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_find.py::test_find_not_found -v`

## Pass / Fail Criteria
- **Pass:** Error raised with full effect listing.
- **Fail:** Opaque error or wrong type.
