---
scenario_id: "UI-03"
title: "apply_pip public signature unchanged (introspection)"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] apply_pip signature"]
tags: [test-scenario, regression, structural]
---

# Scenario UI-03: apply_pip signature unchanged

## Description
Spec Requirement 4 + Sub-Spec 2 STRUCTURAL: `apply_pip` public signature is preserved verbatim.

## Steps
1. Import `apply_pip` from `workshop_video_brain.edit_mcp.pipelines.compositing`.
2. Assert `inspect.signature(apply_pip)` yields parameters exactly: `project, overlay_track, base_track, start_frame, end_frame, layout`.
3. Assert the return annotation is `KdenliveProject`.
4. Assert no new required parameters were introduced.

## Expected Results
- Signature unchanged.

## Execution Tool
bash -- `uv run pytest tests/unit/test_apply_pip_regression.py::test_apply_pip_signature -v`

## Pass / Fail Criteria
- **Pass:** Signature matches pinned expectation.
- **Fail:** Any addition/removal/rename.
