---
scenario_id: "IO-05"
title: "save_preset(scope=workspace) writes YAML and creates stacks/ dir"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-05: save_preset to workspace

## Description
Verifies `[BEHAVIORAL]` -- workspace save writes `<workspace_root>/stacks/<preset.name>.yaml`, creating the `stacks/` directory if it doesn't exist.

## Preconditions
- `tmp_path` workspace root with no `stacks/` subdir.
- A constructed `Preset(name="my-preset", ...)`.

## Steps
1. Confirm `<tmp>/stacks/` does NOT exist.
2. Call `save_preset(preset, workspace_root=tmp, scope="workspace")`.
3. Assert `<tmp>/stacks/` exists (directory created).
4. Assert `<tmp>/stacks/my-preset.yaml` exists.
5. Assert content parses as YAML (`yaml.safe_load`) into a dict.

## Expected Results
- File at the documented path; directory autocreated.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_save_workspace -v`

## Pass / Fail Criteria
- **Pass:** File exists and parses.
- **Fail:** Missing dir/file or invalid YAML.
