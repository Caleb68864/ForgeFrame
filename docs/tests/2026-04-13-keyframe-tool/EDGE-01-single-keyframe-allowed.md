---
scenario_id: "EDGE-01"
title: "Single keyframe permitted; emits static value with operator"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - edge-case
---

# Scenario EDGE-01: Single keyframe allowed

## Description
Verifies the "Single keyframe -- Permitted" edge case -- a single keyframe emits `"HH:MM:SS.mmm=value"` (with easing operator attached if non-linear). MLT treats this as a static value.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Call `build_keyframe_string("scalar", [KF(0, 0.5, "linear")], fps=30.0, ease_family_default="cubic")`.
2. Assert output equals `"00:00:00.000=0.5"`.
3. Call with `KF(0, 0.5, "ease_in_out")`.
4. Assert output equals `"00:00:00.000i=0.5"` (or the family-default operator char).
5. Confirm no spurious trailing semicolon.

## Expected Results
- Single keyframe emits exactly one `time=value` pair with optional easing prefix.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_single_keyframe -v`

## Pass / Fail Criteria
- **Pass:** Output exact.
- **Fail:** Trailing separator, missing operator, or raised error.
