---
scenario_id: "KF-06"
title: "build_keyframe_string emits expected rect animation string"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-06: build_keyframe_string emits expected rect animation string

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- exact MLT output for a two-keyframe rect animation with mixed easing.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Call `build_keyframe_string("rect", [Keyframe(frame=0, value=[0,0,1920,1080,1], easing="linear"), Keyframe(frame=60, value=[100,50,1920,1080,0.5], easing="ease_in_out")], fps=30.0, ease_family_default="cubic")`.
2. Assert the exact return string equals `"00:00:00.000=0 0 1920 1080 1;00:00:02.000i=100 50 1920 1080 0.5"`.
3. Repeat with `ease_family_default="expo"` and assert the second keyframe uses the `expo`-in-out prefix (`r`) instead of `i`.
4. Assert semicolon is the separator, `=` follows the timestamp+operator, space separates rect components.

## Expected Results
- Output matches the spec's sample string byte-for-byte.
- Operator prefix reflects the resolved `ease_family_default` for bare aliases.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_build_rect_string -v`

## Pass / Fail Criteria
- **Pass:** Exact string match.
- **Fail:** Any whitespace/separator/operator drift.
