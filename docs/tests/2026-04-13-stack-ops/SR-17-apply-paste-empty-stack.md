---
scenario_id: "SR-17"
title: "apply_paste with empty effects: [] is a no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
  - edge-case
---

# Scenario SR-17: Empty stack paste no-op

## Description
Verifies `[BEHAVIORAL]` -- pasting `{"source_clip": [...], "effects": []}` on any mode leaves target untouched and returns without error.

## Preconditions
- Target clip with N>=1 known filters.

## Steps
1. Snapshot target's `list_effects` baseline.
2. For each mode in `["append", "prepend", "replace"]`:
   - Call `apply_paste(project, target_ref, {"source_clip":[2,0], "effects":[]}, mode=mode)`.
   - Note: in `replace` mode, the spec is ambiguous; align test to documented behavior of "no-op when incoming empty". If implementation chose to clear-then-add-nothing, mark a sub-assertion.
3. Compare `list_effects` to baseline -- expect identical (for append/prepend at minimum).

## Expected Results
- Append/prepend leave target unchanged.
- No exceptions.
- Replace behavior follows the implementation's documented choice (test asserts that documented choice; default expectation per spec is "no-op").

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_empty -v`

## Pass / Fail Criteria
- **Pass:** No mutation in append/prepend; no error in any mode.
- **Fail:** Spurious mutation or raised error.
