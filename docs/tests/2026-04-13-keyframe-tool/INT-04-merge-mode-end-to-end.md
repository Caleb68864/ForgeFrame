---
scenario_id: "INT-04"
title: "mode='merge' preserves non-overlap and overwrites same-frame"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - behavioral
  - sequential
---

# Scenario INT-04: MCP merge mode end-to-end

## Description
Verifies [BEHAVIORAL] Sub-Spec 4 -- `mode="merge"` on an existing keyframe string preserves non-overlapping frames and overwrites same-frame entries.

Sequential: depends on INT-03 state or uses its own fresh copy.

## Preconditions
- Fresh temp workspace copy of fixture.
- Step 1 seeds initial keyframes via an INT-03-style `replace` call.

## Steps
1. Seed via `effect_keyframe_set_rect(..., mode="replace", keyframes=[KF0, KF60, KF120])`.
2. Call `effect_keyframe_set_rect(..., mode="merge", keyframes=[KF60', KF90])` (KF60' has different value/easing than KF60).
3. Re-read and parse the resulting property.
4. Assert final keyframe list equals `[KF0, KF60', KF90, KF120]` sorted by frame.
5. Assert snapshot id is returned from BOTH calls and they differ.

## Expected Results
- Merge semantics correct at the MCP layer.
- Two distinct snapshot ids.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_merge_mode -v`

## Pass / Fail Criteria
- **Pass:** Final list matches expected.
- **Fail:** Duplicates, lost entries, or merged incorrectly.
