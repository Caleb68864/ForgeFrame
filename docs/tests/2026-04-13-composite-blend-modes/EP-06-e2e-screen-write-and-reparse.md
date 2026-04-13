---
scenario_id: "EP-06"
title: "End-to-end: screen blend mode written to .kdenlive and re-parsed"
tool: "bash"
type: test-scenario
sequential: true
covers: ["[BEHAVIORAL] E2E screen"]
tags: [test-scenario, mcp, behavioral, e2e, critical]
---

# Scenario EP-06: E2E screen blend written + re-parsed

## Description
Spec Sub-Spec 2 BEHAVIORAL: `composite_set(track_a=1, track_b=4, start_frame=0, end_frame=120, blend_mode="screen")` against fixture project -- re-parsing the written `.kdenlive` shows a composite transition between tracks 1 and 4 carrying the screen blend mode value.

## Preconditions
- Workspace created under `tmp_path`.
- Fixture project with >= 4 tracks copied in (use or extend `sample_tutorial.kdenlive`; if it lacks 4 tracks, use `track_add` MCP tool or a purpose-built fixture).

## Steps
1. Set up workspace and copy fixture into it.
2. Call `composite_set(workspace_path=tmp_path, project_file=FIXTURE, track_a=1, track_b=4, start_frame=0, end_frame=120, blend_mode="screen")`.
3. Assert `result["status"] == "ok"`.
4. Re-parse the project file via `parse_project(tmp_path / FIXTURE)`.
5. Locate a composite transition between track 1 and track 4 with `start_frame=0`, `end_frame=120`.
6. Assert the transition's `compositing` (or discovered MLT property) equals `BLEND_MODE_TO_MLT["screen"]`.

## Expected Results
- Composite transition present in the reparsed project with the expected MLT blend-mode value.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_e2e_screen_blend_mode -v`

## Pass / Fail Criteria
- **Pass:** Transition found; MLT value correct.
- **Fail:** Transition missing, on wrong tracks/frames, or with wrong value.
