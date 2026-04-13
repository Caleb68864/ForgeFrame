---
scenario_id: "KF-11"
title: "Empty keyframes list raises ValueError"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - edge-case
---

# Scenario KF-11: Empty keyframes list raises ValueError

## Description
Verifies Sub-Spec 2 edge case -- `build_keyframe_string` called with an empty keyframes list raises `ValueError("keyframes list cannot be empty")`.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Call `build_keyframe_string("scalar", [], fps=30.0, ease_family_default="cubic")`.
2. Assert `ValueError` raised; message contains "empty".
3. Repeat for `kind="rect"` and `kind="color"`.

## Expected Results
- All three kinds raise `ValueError` on empty input.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_empty_list -v`

## Pass / Fail Criteria
- **Pass:** Raised consistently across kinds.
- **Fail:** Returns empty string or silent no-op.
