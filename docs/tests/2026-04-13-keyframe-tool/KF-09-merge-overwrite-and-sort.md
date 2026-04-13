---
scenario_id: "KF-09"
title: "merge_keyframes overwrites same-frame and preserves sorted order"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-09: merge_keyframes overwrite + sort

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- merge overwrites existing keyframes at colliding frames and keeps the merged list sorted by `frame`.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Given existing `[KF(0, A, linear), KF(60, B, linear), KF(120, C, linear)]` and new `[KF(60, B', ease_in_out), KF(90, D, hold)]`, call `merge_keyframes`.
2. Assert result equals `[KF(0, A, linear), KF(60, B', ease_in_out), KF(90, D, hold), KF(120, C, linear)]`.
3. Assert output is strictly sorted by `frame` ascending.
4. Assert the frame-60 entry uses the new value+easing (overwrite wins).

## Expected Results
- Same-frame new keyframe replaces existing.
- Non-colliding frames preserved from both sides.
- Final list sorted.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_merge_overwrite -v`

## Pass / Fail Criteria
- **Pass:** Exact expected list.
- **Fail:** Stacking duplicates, wrong order, or lost entries.
