---
scenario_id: "SR-06"
title: "reorder_effects with from_index == to_index is a no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
  - edge-case
---

# Scenario SR-06: reorder no-op when indices equal

## Description
Verifies `[BEHAVIORAL]` edge case -- calling `reorder_effects(project, clip_ref, i, i)` is a no-op: no error, stack unchanged, no mutation of `project.opaque_elements`.

## Preconditions
- Clip with at least 1 filter.

## Steps
1. Snapshot `project.opaque_elements` order (deep copy of xml strings).
2. `reorder_effects(project, (2,0), 1, 1)`.
3. Assert returns without exception.
4. Assert `project.opaque_elements` xml strings identical to snapshot.

## Expected Results
- Returns cleanly; project state byte-equal to pre-call snapshot.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_reorder_noop -v`

## Pass / Fail Criteria
- **Pass:** No mutation, no error.
- **Fail:** Any mutation or raised error.
