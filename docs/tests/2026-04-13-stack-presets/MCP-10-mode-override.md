---
scenario_id: "MCP-10"
title: "effect_stack_apply with mode='replace' overrides preset stack_order"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
sequential: true
---

# Scenario MCP-10: MCP apply mode override

## Description
Verifies `[BEHAVIORAL]` -- when `mode="replace"` is passed to `effect_stack_apply`, it overrides the preset's `apply_hints.stack_order` (e.g., even if the preset says `"append"`).

## Preconditions
- Saved preset with `apply_hints.stack_order="append"`.
- Target clip with M=2 pre-existing filters.
- N=2 effects in preset.

## Steps
1. Call `effect_stack_apply(..., name="p", mode="replace")`.
2. Assert response `data.mode == "replace"`.
3. Assert `len(patcher.list_effects(project, tgt_ref)) == 2` (only preset filters; pre-existing cleared).
4. As a control, repeat with `mode=""` against a fresh target -- assert `mode == "append"` and post-count == 4.

## Expected Results
- mode override wins.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_apply_mode_override -v`

## Pass / Fail Criteria
- **Pass:** Override active.
- **Fail:** Preset hint won when override given.
