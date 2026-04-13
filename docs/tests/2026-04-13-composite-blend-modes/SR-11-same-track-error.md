---
scenario_id: "SR-11"
title: "track_a == track_b raises ValueError"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] same-track error"]
tags: [test-scenario, pipeline, behavioral, critical, error-path]
---

# Scenario SR-11: track_a == track_b raises ValueError

## Description
Compositing a track against itself is nonsensical -- must raise `ValueError` (spec Requirement 9).

## Preconditions
- Module implemented.

## Steps
1. Build a project.
2. Call `apply_composite(project, track_a=2, track_b=2, start_frame=0, end_frame=30, blend_mode="screen")` inside `pytest.raises(ValueError)`.
3. Assert the error message clarifies the problem (mentions tracks/same).

## Expected Results
- `ValueError` raised with clarifying message.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_same_tracks -v`

## Pass / Fail Criteria
- **Pass:** ValueError raised; message references the same-track issue.
- **Fail:** No exception, silent pass, or wrong exception type.
