---
scenario_id: "EDGE-02"
title: "MLT version guard fires when workspace pins MLT<7.22"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - edge-case
---

# Scenario EDGE-02: MLT version guard

## Description
Verifies the MLT version guard -- if `smooth_natural`, `smooth_tight`, `$=`, or `-=` is requested AND workspace metadata pins MLT<7.22, the pipeline raises with a version-requirement message. For MLT>=7.22 (including the current target 7.36), no guard fires.

## Preconditions
- Workspace loader importable.
- Ability to construct a workspace with `mlt_version: "7.20"` (or similar) for the guard case.

## Steps
1. Construct workspace with MLT 7.20 pin.
2. Invoke keyframe build (or MCP tool) requesting easing `smooth_natural`.
3. Assert raises with message identifying the required MLT version and the triggering easing.
4. Repeat with `smooth_tight`, raw `$=`, raw `-=` -- all raise.
5. Change workspace MLT pin to 7.36; repeat each -- none raise.
6. Confirm the guard check is NOT on the hot path for common-case operators (e.g., `linear`, `smooth`, `ease_in_out`).

## Expected Results
- Guard fires only for the four listed easings AND only when MLT<7.22.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_mlt_version_guard -v`

## Pass / Fail Criteria
- **Pass:** Guard correct for both branches; no false positives.
- **Fail:** Always fires, never fires, or wrong easing set.
