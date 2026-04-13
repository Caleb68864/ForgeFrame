---
scenario_id: "SR-07"
title: "Default geometry applied when geometry=None"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] default geometry"]
tags: [test-scenario, pipeline, behavioral]
---

# Scenario SR-07: Default geometry applied when geometry=None

## Description
When `geometry` is omitted/`None`, the function must emit full-frame geometry `"0/0:WxH:100"` where W and H come from the project's profile.

## Preconditions
- Known profile dimensions (use 1920x1080 fixture).

## Steps
1. Build/parse a project with profile width=1920, height=1080.
2. Call `apply_composite(project, track_a=1, track_b=2, start_frame=0, end_frame=30, blend_mode="cairoblend")` (no `geometry` arg).
3. Extract params dict from the resulting composition.
4. Assert `params["geometry"] == "0/0:1920x1080:100"`.

## Expected Results
- Default geometry string exactly matches `"0/0:{width}x{height}:100"`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_default_geometry -v`

## Pass / Fail Criteria
- **Pass:** Geometry matches full-frame default.
- **Fail:** Missing geometry key or wrong default string.
