---
scenario_id: "SR-03"
title: "apply_composite exported with spec signature"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] apply_composite signature"]
tags: [test-scenario, pipeline, structural]
---

# Scenario SR-03: apply_composite exported with spec signature

## Description
Uses `inspect.signature` to verify `apply_composite` exposes the exact parameters, defaults, and return annotation from Requirement 1 / Sub-Spec 1.

## Preconditions
- Module implemented.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines.compositing import apply_composite`.
2. `sig = inspect.signature(apply_composite)`.
3. Assert parameter names in order: `project, track_a, track_b, start_frame, end_frame, blend_mode, geometry`.
4. Assert `sig.parameters["blend_mode"].default == "cairoblend"`.
5. Assert `sig.parameters["geometry"].default is None`.
6. Assert return annotation is `KdenliveProject` (import and compare).

## Expected Results
- Signature matches spec exactly.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_signature -v`

## Pass / Fail Criteria
- **Pass:** All inspect assertions pass.
- **Fail:** Any parameter name, default, or annotation mismatch.
