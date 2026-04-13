---
scenario_id: "FIND-01"
title: "effect_find resolves by kdenlive_id first"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - effect-find
  - behavioral
---

# Scenario FIND-01: effect_find resolves by kdenlive_id preferred

## Description
Verifies [STRUCTURAL] + [BEHAVIORAL] Sub-Spec 3 -- `find(project, clip_ref, name)` returns the index of the filter whose `kdenlive_id` matches the name, preferring this over `mlt_service`.

## Preconditions
- Fixture project or in-memory tree with at least two filters on the target clip:
  - filter[0]: `mlt_service="affine"`, `kdenlive_id="transform"`
  - filter[1]: `mlt_service="brightness"`, `kdenlive_id="brightness"`

## Steps
1. Call `find(project, (2, 0), "transform")`.
2. Assert return value is `0`.
3. Add a third filter with `mlt_service="transform"` (no `kdenlive_id`) after the one already matching `kdenlive_id="transform"`; repeat -- assert still returns index `0` (kdenlive_id match wins over later `mlt_service` match).

## Expected Results
- Preference order: `kdenlive_id` match -> fall back to `mlt_service`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_find.py::test_find_prefers_kdenlive_id -v`

## Pass / Fail Criteria
- **Pass:** Returns `kdenlive_id` match even when a later `mlt_service` would match.
- **Fail:** Wrong index or fallback ordering inverted.
