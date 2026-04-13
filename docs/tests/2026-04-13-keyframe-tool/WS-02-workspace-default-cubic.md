---
scenario_id: "WS-02"
title: "Missing keyframe_defaults section yields default 'cubic'"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - workspace
  - behavioral
  - edge-case
---

# Scenario WS-02: Default ease_family is cubic

## Description
Verifies [BEHAVIORAL] Sub-Spec 3 edge case -- loading a `workspace.yaml` with NO `keyframe_defaults` section yields `workspace.keyframe_defaults.ease_family == "cubic"` (hardcoded fallback).

## Preconditions
- Workspace loader importable.
- Temp `workspace.yaml` with no `keyframe_defaults` key.

## Steps
1. Create temp `workspace.yaml` omitting `keyframe_defaults`.
2. Load the workspace.
3. Assert `workspace.keyframe_defaults.ease_family == "cubic"`.
4. Confirm no warning or error is emitted.

## Expected Results
- Default applied silently.

## Execution Tool
bash -- `uv run pytest tests/unit/test_workspace_keyframe_defaults.py::test_default_cubic -v`

## Pass / Fail Criteria
- **Pass:** Default is `"cubic"`.
- **Fail:** Other value, None, or load error.
