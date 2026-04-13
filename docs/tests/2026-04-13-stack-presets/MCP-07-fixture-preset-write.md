---
scenario_id: "MCP-07"
title: "effect_stack_preset against fixture writes valid YAML parsing back to Preset"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
sequential: true
---

# Scenario MCP-07: end-to-end preset save against fixture

## Description
Verifies `[BEHAVIORAL]` -- against `keyframe_project.kdenlive`, `effect_stack_preset(track=2, clip=0, name="test-preset")` writes `<ws>/stacks/test-preset.yaml`; the file exists and parses back into a `Preset` with `effect_count >= 1`.

## Preconditions
- Fixture copied to ephemeral workspace.

## Steps
1. Call `effect_stack_preset(workspace_path=ws, project_file=fixture_copy, track=2, clip=0, name="test-preset")`.
2. Assert response `status == "ok"`.
3. Assert `<ws>/stacks/test-preset.yaml` exists.
4. `load_preset("test-preset", ws, vault=None)` -> assert returns a `Preset` with `len(preset.effects) >= 1`.
5. Assert response `data.effect_count == len(preset.effects)`.

## Expected Results
- File written; round-trips through `load_preset`; effect count consistent.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_preset_against_fixture -v`

## Pass / Fail Criteria
- **Pass:** All assertions hold.
- **Fail:** Otherwise.
