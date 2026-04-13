---
scenario_id: "EP-14"
title: "Non-adjacent tracks (1 <-> 4) allowed"
tool: "bash"
type: test-scenario
sequential: true
covers: ["Edge: non-adjacent tracks"]
tags: [test-scenario, mcp, behavioral, edge-case]
---

# Scenario EP-14: Non-adjacent tracks allowed

## Description
Spec Edge Case: composite between track_a=1 and track_b=4 (with intervening tracks) is allowed.

## Steps
1. Set up workspace with a fixture containing >= 4 tracks.
2. Call `composite_set(..., track_a=1, track_b=4, blend_mode="screen", start_frame=0, end_frame=60)`.
3. Assert `result["status"] == "ok"`.
4. Re-parse and confirm the composite transition spans tracks 1 and 4.

## Expected Results
- Non-adjacent composite accepted and persisted.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_non_adjacent_tracks -v`

## Pass / Fail Criteria
- **Pass:** Composition added between 1 and 4.
- **Fail:** Rejection or wrong-track transition.
