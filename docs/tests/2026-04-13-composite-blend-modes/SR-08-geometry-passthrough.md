---
scenario_id: "SR-08"
title: "Explicit geometry string passes through unchanged"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] geometry passthrough"]
tags: [test-scenario, pipeline, behavioral]
---

# Scenario SR-08: Explicit geometry string passes through unchanged

## Description
Caller-provided geometry strings (even odd ones) are written verbatim; `apply_composite` does NOT validate geometry structure (per spec Edge Cases).

## Preconditions
- Module implemented.

## Steps
1. Build a project.
2. Call `apply_composite(..., geometry="100/50:1920x1080:75")`.
3. Assert `params["geometry"] == "100/50:1920x1080:75"`.
4. Repeat with a deliberately malformed string (e.g. `"banana"`) and assert the string is still passed through (no ValueError from `apply_composite`).

## Expected Results
- Geometry preserved byte-for-byte.
- No pre-validation.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_geometry_passthrough -v`

## Pass / Fail Criteria
- **Pass:** Geometry string round-trips unchanged; malformed string not rejected here.
- **Fail:** String mutated, normalized, or rejected.
