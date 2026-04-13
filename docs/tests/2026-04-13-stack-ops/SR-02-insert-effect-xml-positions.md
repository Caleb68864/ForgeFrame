---
scenario_id: "SR-02"
title: "insert_effect_xml at top, bottom, and middle"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario SR-02: insert_effect_xml at top, bottom, and middle

## Description
Verifies `[BEHAVIORAL]` placement semantics: position=0 places at top of clip stack, position=len(stack) places at bottom, mid-stack position lands at correct relative index. Confirms the absolute index within `project.opaque_elements` is computed correctly relative to the `after_tractor` slot used by `_apply_add_effect`.

## Preconditions
- Parsed Kdenlive project with target clip (e.g. `(2,0)`) carrying a known number of filters.
- Helper to build an `OpaqueElement` filter XML string for a known service.

## Steps
1. Load fixture project; capture initial `list_effects((2,0))` -- denote N entries.
2. `insert_effect_xml(project, (2,0), xml_string=<new_filter_xml>, position=0)`; call `list_effects` -- assert new filter is index 0, original entries shifted to 1..N.
3. Reload fixture; `insert_effect_xml(... position=N)`; assert new filter is at index N (bottom).
4. Reload fixture (with N>=2); `insert_effect_xml(... position=1)`; assert new filter is at index 1, prior index-1..N-1 shifted by one.
5. After each insert, scan `project.opaque_elements` order; assert filter elements for unrelated clips are unchanged.

## Expected Results
- Insertion at position 0 yields top-of-stack.
- Insertion at position len(stack) yields bottom-of-stack.
- Mid-stack insertion preserves relative order of unaffected filters.
- Other clips' filters untouched.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_insert_positions -v`

## Pass / Fail Criteria
- **Pass:** All three positions verified plus other clips unaffected.
- **Fail:** Any positional miscount, side-effect on unrelated clips, or absolute-index miscomputation.
