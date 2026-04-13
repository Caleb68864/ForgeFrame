---
scenario_id: "EDGE-05"
title: "Serializer output unchanged for non-keyframe properties"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - edge-case
  - sequential
---

# Scenario EDGE-05: Serializer output unchanged for non-keyframe properties

## Description
Verifies the "Must Nots: must NOT change `.kdenlive` serializer output for non-keyframe properties" constraint -- after a keyframe tool mutates ONE property, every OTHER property + element in the project serializes byte-for-byte identically to the pre-call state.

## Preconditions
- Fixture project with multiple clips, filters, and assorted property types.
- Ability to capture the serialized output before and after a call.

## Steps
1. Serialize fixture project to a temp file; save as `before.kdenlive`.
2. Invoke `effect_keyframe_set_rect` on clip `(2, 0)`, effect_index `0`, property `rect`.
3. Serialize the resulting project to `after.kdenlive`.
4. Diff the two files. Assert the ONLY differences are:
   - The `<property name="rect">` text on the targeted filter.
   - Any minimal snapshot metadata expected by the auto-snapshot policy (if stored in-tree).
5. Assert no whitespace drift, no attribute reordering, no element reordering anywhere else in the file.

## Expected Results
- Diff scope strictly bounded to the target property (+ documented snapshot metadata).

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_serializer_untouched -v`

## Pass / Fail Criteria
- **Pass:** Diff bounded.
- **Fail:** Any unrelated tree drift.
