---
scenario_id: "SR-16"
title: "effect_fade writes opacity keyframes on transform rect"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - fade
sequential: true
---

# Scenario SR-16: `effect_fade` keyframes on transform `rect`

## Preconditions
- Workspace with a clip at track=2 clip=0, total_frames known (e.g., 120).

## Steps
1. Call `effect_fade(workspace, project, track=2, clip=0, fade_in_frames=30, fade_out_frames=30, easing="ease_in_out")`.
2. Re-parse project; locate the inserted `transform` filter on target clip.
3. Inspect the `rect` property keyframe string.
4. Assert the keyframe count is 2 or 4 (start + end, optionally plus pre-fade-in/post-fade-out).
5. Assert the opacity component of each keyframe has the expected values at t=0 (0.0), t=fade_in_frames (1.0), t=total-fade_out (1.0), t=total (0.0).
6. Call `build_fade_keyframes(30, 30, 120, 30, "ease_in_out")` directly and assert it returns a non-empty string in MLT keyframe format.

## Expected Results
- Transform filter present with rect keyframes encoding opacity ramp.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_fade_keyframes -v`

## Pass / Fail Criteria
- **Pass:** keyframes present with expected opacity values.
- **Fail:** missing keyframes or wrong property.
