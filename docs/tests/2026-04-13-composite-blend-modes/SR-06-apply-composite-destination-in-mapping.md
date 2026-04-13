---
scenario_id: "SR-06"
title: "apply_composite(destination_in) uses mapped MLT value"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] destination_in happy path", "BLEND_MODE_TO_MLT mapping coverage"]
tags: [test-scenario, pipeline, behavioral, critical]
---

# Scenario SR-06: apply_composite(destination_in) uses mapped MLT value

## Description
Verifies that a mode with potentially non-identity MLT mapping (`destination_in`, spec example `dst-in`) is correctly translated through `BLEND_MODE_TO_MLT` before being written into `AddComposition.params`.

## Preconditions
- Module implemented.

## Steps
1. Build/parse a minimal `KdenliveProject` with >= 2 tracks.
2. Call `apply_composite(project, track_a=1, track_b=2, start_frame=0, end_frame=60, blend_mode="destination_in")`.
3. Extract the composition's params dict.
4. Assert the mapped value equals `BLEND_MODE_TO_MLT["destination_in"]` (NOT the literal string `"destination_in"` unless identity mapping is documented).

## Expected Results
- Params dict contains the mapped MLT identifier for destination_in.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_destination_in -v`

## Pass / Fail Criteria
- **Pass:** Written MLT value matches the mapping table exactly.
- **Fail:** Raw abstract string written without mapping, or wrong value.
