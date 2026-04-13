---
scenario_id: "SR-11"
title: "serialize_stack on zero-filter clip returns effects: []"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
  - edge-case
---

# Scenario SR-11: serialize empty stack

## Description
Verifies `[BEHAVIORAL]` edge case -- serializing a clip with no filters yields `{"source_clip": [t,c], "effects": []}` and does NOT raise.

## Preconditions
- A clip with zero filters (use `remove_effect` to clear an existing clip, or pick an unmodified clip).

## Steps
1. Identify or construct clip_ref with `list_effects(... ) == []`.
2. `stack = serialize_stack(project, clip_ref)`.
3. Assert no exception.
4. Assert `stack["effects"] == []`.
5. Assert `stack["source_clip"]` matches the clip_ref.

## Expected Results
- Empty list returned, no error.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_serialize_empty -v`

## Pass / Fail Criteria
- **Pass:** Empty effects list, no error.
- **Fail:** Raised exception or non-empty/incorrect dict.
