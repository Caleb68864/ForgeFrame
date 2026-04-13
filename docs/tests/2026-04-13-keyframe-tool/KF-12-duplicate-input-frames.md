---
scenario_id: "KF-12"
title: "Duplicate input frames: later wins with warning"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - edge-case
---

# Scenario KF-12: Duplicate frames in input -- later wins + warning

## Description
Verifies Sub-Spec 2 edge case -- duplicate frames within one call are deduplicated; the later entry wins; one warning is emitted.

## Preconditions
- `pipelines/keyframes.py` importable. Warning surface is documented (return payload log line, Python `warnings`, or structured log).

## Steps
1. Build with keyframes `[KF(30, A, linear), KF(30, B, ease_in), KF(60, C, linear)]`.
2. Assert emitted string encodes only two unique frames (30 and 60).
3. Assert the frame-30 value+easing is `B/ease_in` (later wins).
4. Assert exactly one warning was emitted (capture via `pytest.warns` or equivalent capture hook).

## Expected Results
- Later duplicate overrides earlier.
- Exactly one warning, not error.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_duplicate_frames -v`

## Pass / Fail Criteria
- **Pass:** Dedup correct, warning emitted once.
- **Fail:** Stacked duplicates, first-wins, silent dedup, or raised error.
