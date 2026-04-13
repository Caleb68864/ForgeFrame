---
scenario_id: "SR-05"
title: "apply_composite(screen) emits AddComposition with correct MLT key/value"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] screen happy path"]
tags: [test-scenario, pipeline, behavioral, critical]
---

# Scenario SR-05: apply_composite(screen) happy path

## Description
Calling `apply_composite` with `blend_mode="screen"` must produce a project containing an `AddComposition`-derived composite transition whose `params` dict carries `{BLEND_MODE_MLT_PROPERTY: BLEND_MODE_TO_MLT["screen"]}` (plus geometry).

## Preconditions
- A minimal `KdenliveProject` fixture with >= 2 tracks and a known profile (e.g. 1920x1080).
- Profile width/height exposed via `project.profile`.

## Steps
1. Build a minimal `KdenliveProject` (or load `tests/fixtures/projects/sample_tutorial.kdenlive` via `parse_project`).
2. Call `updated = apply_composite(project, track_a=1, track_b=2, start_frame=0, end_frame=120, blend_mode="screen")`.
3. Inspect the resulting project: locate the newly added composite transition between tracks 1 and 2 starting at frame 0 and ending at frame 120.
4. Assert the transition's parameters (or, if the test inspects the intent list produced before patching, the intercepted `AddComposition.params`) include the key `BLEND_MODE_MLT_PROPERTY` with value `BLEND_MODE_TO_MLT["screen"]`.
5. Assert `composition_type == "composite"`.
6. Assert geometry key present and valued for full-frame default (see SR-07 for default contract).

## Expected Results
- A composite composition is added on the correct tracks/frames.
- Params dict contains the correct MLT blend-mode key and value.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_screen -v`

## Pass / Fail Criteria
- **Pass:** Composition added with correct type, tracks, frames, and blend-mode key/value.
- **Fail:** Missing composition, wrong composition_type, missing or wrong blend-mode key/value.
