---
scenario_id: "SR-16"
title: "apply_paste rewrites track= and clip_index= XML attributes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
---

# Scenario SR-16: Attribute rewriting on paste

## Description
Verifies `[BEHAVIORAL]` -- pasting filters originally tagged with the source's `track=` / `clip_index=` rewrites those attributes to match the target clip_ref. Even if source attrs are missing or malformed, paste sets them correctly on the target.

## Preconditions
- Source clip (2,0) with at least one filter; target clip (3,1).
- Optional adversarial fixture: a stack dict whose effect xml omits `track=`/`clip_index=`.

## Steps
1. `stack = serialize_stack(project, (2,0))`; confirm each effect xml contains `track="2"` and `clip_index="0"`.
2. `apply_paste(project, (3,1), stack, mode="append")`.
3. Re-parse target's filters; assert each pasted filter's xml contains `track="3"` and `clip_index="1"`.
4. Assert no remnant `track="2"` / `clip_index="0"` on target's pasted filters.
5. Repeat with adversarial stack dict missing those attrs; assert paste still inserts filters with correct target attrs.

## Expected Results
- All pasted filters carry target's track/clip_index attributes.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_attr_rewrite -v`

## Pass / Fail Criteria
- **Pass:** Attributes rewritten on every pasted filter.
- **Fail:** Source attrs leaked, missing attrs not added.
