---
scenario_id: "KF-08"
title: "build+parse round-trip for scalar, rect, and color"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-08: build+parse round-trip for scalar/rect/color

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- `parse_keyframe_string` inverts `build_keyframe_string` for all three kinds.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. For `kind="scalar"`: build from a list of keyframes with mixed easing and float values, parse the result, assert parsed list equals original (modulo numeric coercion rules documented in spec).
2. For `kind="rect"`: build with 5-tuples and varied easing; parse; assert equality.
3. For `kind="color"`: build from a list of hex or `#RRGGBBAA` color values; parse; assert equality.
4. Include at least one `linear` (empty-prefix) keyframe per kind.
5. Include at least one raw-operator easing (e.g., `$=`) per kind.

## Expected Results
- `parse(build(x)) == x` for all three kinds, across all documented easing forms.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_round_trip -v`

## Pass / Fail Criteria
- **Pass:** All three kinds round-trip cleanly.
- **Fail:** Any kind loses easing, value, or frame.
