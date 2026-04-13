---
scenario_id: "MCP-12"
title: "effect_stack_apply response includes blend/track/required hints verbatim"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
sequential: true
---

# Scenario MCP-12: Apply response surfaces hints

## Description
Verifies `[BEHAVIORAL]` -- the MCP apply response surfaces `blend_mode_hint`, `track_placement_hint`, `required_producers_hint` verbatim from the preset's `apply_hints`.

## Preconditions
- Saved preset with `apply_hints = {blend_mode: "screen", stack_order: "append", track_placement: "V2", required_producers: ["audio.wav"]}`.

## Steps
1. Call `effect_stack_apply(..., name="p", mode="")`.
2. Assert `data.blend_mode_hint == "screen"`.
3. Assert `data.track_placement_hint == "V2"`.
4. Assert `data.required_producers_hint == ["audio.wav"]` (or tuple equivalent in JSON form).

## Expected Results
- Hints verbatim.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_apply_hints_surfaced -v`

## Pass / Fail Criteria
- **Pass:** All hints match.
- **Fail:** Otherwise.
