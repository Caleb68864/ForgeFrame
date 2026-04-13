---
scenario_id: "KF-13"
title: "Time-conversion collision errors with both entries"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - edge-case
---

# Scenario KF-13: Time-conversion collision

## Description
Verifies Sub-Spec 2 edge case -- when two input keyframes use different time forms that normalize to the same MLT timestamp, an error is raised naming both offending entries.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Build with `[KF(frame=59, ..., linear), KF(seconds=1.967, ..., linear)]` at fps=30 (both -> `00:00:01.967`).
2. Assert raises `ValueError` (or specific `TimeCollisionError` if introduced); message includes BOTH original time inputs.
3. Confirm this is distinct from KF-12 (same-frame dedup) -- collision via conversion must error, not dedup.

## Expected Results
- Error raised listing both colliding original inputs.
- Contrasts with intra-call dedup behavior (KF-12 dedups on identical resolved frame directly provided).

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_time_conversion_collision -v`

## Pass / Fail Criteria
- **Pass:** Error raised with both original inputs in message.
- **Fail:** Silent dedup or opaque error.
