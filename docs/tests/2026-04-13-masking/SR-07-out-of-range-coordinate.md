---
scenario_id: "SR-07"
title: "shape_to_points — out-of-range coordinate raises ValueError naming offender"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-07: shape_to_points — out-of-range coordinate raises ValueError naming offender

## Description
Verifies [BEHAVIORAL] strict normalized `[0, 1]` range validation. Any bound or point coordinate that is negative or greater than 1 raises `ValueError` whose message names the offending value.

## Preconditions
- Module importable.

## Steps
1. Call `shape_to_points(MaskShape(kind="rect", bounds=(-0.1, 0, 0.5, 0.5)))` — expect `ValueError` message containing `-0.1`.
2. Call `shape_to_points(MaskShape(kind="rect", bounds=(0, 0, 1.2, 0.5)))` — expect `ValueError` message containing `1.2`.
3. Call `shape_to_points(MaskShape(kind="polygon", points=((0.1, 0.1), (1.5, 0.1), (0.3, 0.5))))` — expect `ValueError` message containing `1.5`.
4. Call `shape_to_points(MaskShape(kind="rect", bounds=(0, 0, 0, 0.5)))` — expect `ValueError` (w=0, per Edge Cases).
5. Per Musts: must NOT silently clamp.

## Expected Results
- Each case raises `ValueError`.
- Each message contains the exact offending numeric value.
- No silent clamping or default substitution.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_shape_to_points_out_of_range -v`

## Pass / Fail Criteria
- **Pass:** all 4 cases raise with offender in message.
- **Fail:** any case silently succeeds or lacks offender in message.
