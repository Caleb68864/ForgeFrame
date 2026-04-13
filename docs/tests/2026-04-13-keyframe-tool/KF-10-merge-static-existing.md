---
scenario_id: "KF-10"
title: "merge handles static non-keyframe existing value"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
  - edge-case
---

# Scenario KF-10: merge_keyframes handles static existing value

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 edge case -- when merging against an existing static value (no `;`, no `=`), the static is treated as a single keyframe at frame 0 with linear easing, then merged.

## Preconditions
- `pipelines/keyframes.py` importable. Note: this case may be exercised via the public API that accepts raw existing strings, depending on interface. Test the specific path used by the MCP tool.

## Steps
1. Simulate existing property `"0 0 1920 1080 1"` (static rect, no keyframes).
2. Attempt merge with new `[KF(60, [100,50,1920,1080,0.5], ease_in_out)]`.
3. Assert the resulting keyframe list is `[KF(0, [0,0,1920,1080,1], linear), KF(60, [100,50,1920,1080,0.5], ease_in_out)]`.
4. Repeat for a scalar static value like `"0.5"`.
5. Repeat for a color static value.

## Expected Results
- Static is lifted to frame-0 linear keyframe.
- New keyframes merged on top.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_merge_static_existing -v`

## Pass / Fail Criteria
- **Pass:** Static correctly interpreted and merged.
- **Fail:** Static dropped, duplicated, or mis-parsed.
