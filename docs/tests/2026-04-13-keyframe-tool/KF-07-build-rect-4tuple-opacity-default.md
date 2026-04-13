---
scenario_id: "KF-07"
title: "build accepts 4-tuple rect and defaults opacity to 1"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-07: build accepts 4-tuple rect and defaults opacity to 1

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- `build_keyframe_string` accepts 4-tuple `[x,y,w,h]` values and emits `x y w h 1` (opacity=1 default). Also accepts 5-tuple explicitly.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Build with single keyframe `value=[10, 20, 1280, 720]` (4-tuple); assert output contains `"10 20 1280 720 1"`.
2. Build with `value=[10, 20, 1280, 720, 0.75]` (5-tuple); assert output contains `"10 20 1280 720 0.75"`.
3. Build with mixed list (one 4-tuple, one 5-tuple) across two frames; assert both normalized correctly.
4. Build with invalid-arity tuple (3 or 6 elements); assert `ValueError` with arity message.

## Expected Results
- 4-tuple -> opacity appended as `1`.
- 5-tuple preserved.
- Wrong arity rejected.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_rect_tuple_arity -v`

## Pass / Fail Criteria
- **Pass:** Both arities supported and invalid rejected.
- **Fail:** Missing opacity, wrong default, or silent acceptance of wrong arity.
