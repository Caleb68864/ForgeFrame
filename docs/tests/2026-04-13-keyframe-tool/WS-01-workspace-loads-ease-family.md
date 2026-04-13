---
scenario_id: "WS-01"
title: "Workspace loads keyframe_defaults.ease_family from workspace.yaml"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - workspace
  - behavioral
  - structural
---

# Scenario WS-01: Workspace loads ease_family

## Description
Verifies [STRUCTURAL]+[BEHAVIORAL] Sub-Spec 3 -- loading a `workspace.yaml` containing `keyframe_defaults.ease_family: "expo"` yields `workspace.keyframe_defaults.ease_family == "expo"`.

## Preconditions
- Workspace loader importable.
- Temp directory with a minimal `workspace.yaml` containing the `keyframe_defaults` section.

## Steps
1. Create a temp `workspace.yaml` with content:
   ```
   keyframe_defaults:
     ease_family: expo
   ```
   plus any other required workspace fields.
2. Load the workspace via the loader.
3. Assert `workspace.keyframe_defaults.ease_family == "expo"`.
4. Repeat for each valid value: `sine, quad, cubic, quart, quint, expo, circ, back, elastic, bounce`.

## Expected Results
- Each valid value round-trips through yaml load.
- Field is present on the pydantic model and typed via `Literal`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_workspace_keyframe_defaults.py::test_load_valid_ease_family -v`

## Pass / Fail Criteria
- **Pass:** All ten valid values load.
- **Fail:** Any load failure or attribute missing.
