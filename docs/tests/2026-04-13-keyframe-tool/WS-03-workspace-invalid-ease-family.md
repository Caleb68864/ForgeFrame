---
scenario_id: "WS-03"
title: "Invalid ease_family raises validation error at load time"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - workspace
  - behavioral
  - edge-case
---

# Scenario WS-03: Invalid ease_family fails fast at load

## Description
Verifies [BEHAVIORAL] Sub-Spec 3 edge case -- loading a `workspace.yaml` with `keyframe_defaults.ease_family: "invalid"` raises a validation error at LOAD time (fail fast), not deferred to keyframe call time.

## Preconditions
- Workspace loader importable.
- Temp `workspace.yaml` with `ease_family: invalid`.

## Steps
1. Create temp `workspace.yaml` with `keyframe_defaults: { ease_family: "invalid" }`.
2. Attempt to load the workspace.
3. Assert a validation error (Pydantic `ValidationError` or equivalent) is raised.
4. Assert the error message lists the valid Literal values.
5. Confirm the error is raised during load, not on first keyframe-tool call (inspect traceback origin).

## Expected Results
- Fail fast at load.
- Valid options listed in error.

## Execution Tool
bash -- `uv run pytest tests/unit/test_workspace_keyframe_defaults.py::test_invalid_ease_family -v`

## Pass / Fail Criteria
- **Pass:** Validation error at load with full valid-value list.
- **Fail:** Late error, silent acceptance, or opaque message.
