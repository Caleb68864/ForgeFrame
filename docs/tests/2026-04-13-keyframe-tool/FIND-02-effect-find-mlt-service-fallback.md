---
scenario_id: "FIND-02"
title: "effect_find falls back to mlt_service when no kdenlive_id match"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - effect-find
  - behavioral
---

# Scenario FIND-02: effect_find mlt_service fallback

## Description
Verifies [BEHAVIORAL] Sub-Spec 3 -- when no filter has a matching `kdenlive_id`, fall back to `mlt_service` match.

## Preconditions
- Fixture clip with a filter whose `mlt_service="affine"` and whose `kdenlive_id` is absent or different.

## Steps
1. Call `find(project, (2, 0), "affine")`.
2. Assert returns the index of the filter whose `mlt_service="affine"`.
3. Confirm no filter on that clip has `kdenlive_id="affine"` (precondition for the fallback path).

## Expected Results
- Returns correct index via `mlt_service` fallback.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_find.py::test_find_mlt_service_fallback -v`

## Pass / Fail Criteria
- **Pass:** Correct index returned.
- **Fail:** LookupError despite fallback match available.
