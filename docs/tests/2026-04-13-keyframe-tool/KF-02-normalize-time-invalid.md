---
scenario_id: "KF-02"
title: "normalize_time raises ValueError on invalid input"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
  - edge-case
---

# Scenario KF-02: normalize_time raises ValueError on invalid input

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- invalid time input (empty dict, negative frame, malformed timestamp) raises `ValueError` naming the offending key.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Call `normalize_time({}, 30.0)` -- assert `ValueError`; message mentions all three accepted keys.
2. Call `normalize_time({"frame": -1}, 30.0)` -- assert `ValueError`; message mentions `frame`.
3. Call `normalize_time({"timestamp": "nope"}, 30.0)` -- assert `ValueError`; message mentions `timestamp`.
4. Call `normalize_time({"seconds": -0.1}, 30.0)` -- assert `ValueError`; message mentions `seconds`.
5. Call `normalize_time({"frame": 10, "seconds": 2.0}, 30.0)` -- behavior documented: either first-wins or raise (whichever spec author chose); assert deterministic and documented.

## Expected Results
- `ValueError` raised in each invalid case.
- Offending key referenced in the error message.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_normalize_time_invalid -v`

## Pass / Fail Criteria
- **Pass:** All invalid inputs raise with actionable messages.
- **Fail:** Silent acceptance, wrong exception type, or opaque message.
