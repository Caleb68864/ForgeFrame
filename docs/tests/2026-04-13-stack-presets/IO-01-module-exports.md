---
scenario_id: "IO-01"
title: "Module exports Preset/PresetEffect/ApplyHints + save/load/list/resolve_vault_root"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - structural
---

# Scenario IO-01: stack_presets module exports

## Description
Verifies `[STRUCTURAL]` -- `workshop_video_brain.edit_mcp.pipelines.stack_presets` exposes the documented public surface for Sub-Spec 1.

## Preconditions
- `uv sync` complete.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines import stack_presets`.
2. Assert each name resolves: `Preset`, `PresetEffect`, `ApplyHints`, `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root`.
3. Assert `Preset`, `PresetEffect`, `ApplyHints` are subclasses of `pydantic.BaseModel`.
4. Assert `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root` are callables.

## Expected Results
- All seven names importable; classes are Pydantic models; functions callable.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_module_exports -v`

## Pass / Fail Criteria
- **Pass:** All seven names present with correct types.
- **Fail:** Any missing or wrong type.
