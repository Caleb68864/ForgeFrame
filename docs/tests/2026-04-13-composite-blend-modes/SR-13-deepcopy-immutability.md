---
scenario_id: "SR-13"
title: "apply_composite does not mutate input project"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] deepcopy immutability"]
tags: [test-scenario, pipeline, behavioral]
---

# Scenario SR-13: apply_composite does not mutate input project

## Description
Spec Sub-Spec 1: "returns a new `KdenliveProject` (deep copy) with the composition added; original project is unchanged."

## Preconditions
- Module implemented.

## Steps
1. Build/parse a project, capture `original_snapshot = project.model_dump(mode='json')` (or serializer output).
2. Call `updated = apply_composite(project, 1, 2, 0, 60, blend_mode="screen")`.
3. Assert `updated is not project`.
4. Assert `project.model_dump(mode='json') == original_snapshot` (original unchanged).
5. Assert `updated.model_dump(mode='json') != original_snapshot` (new has the composition).

## Expected Results
- Original project untouched; returned object is a distinct copy with the addition.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_immutability -v`

## Pass / Fail Criteria
- **Pass:** Original bytes match snapshot; updated differs.
- **Fail:** Mutation of caller's project, or returned same reference.
