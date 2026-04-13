---
scenario_id: "MCP-03"
title: "effect_stack_apply signature and return envelope"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario MCP-03: effect_stack_apply envelope shape

## Description
Verifies `[STRUCTURAL]` -- `effect_stack_apply(workspace_path, project_file, track, clip, name, mode: str = "")` returns `{"status","data":{"effects_applied","mode","snapshot_id","blend_mode_hint","track_placement_hint","required_producers_hint"}}`. `mode=""` means use preset's hint.

## Preconditions
- A saved preset and a fixture project.

## Steps
1. Inspect signature; assert default `mode=""`.
2. Call with `mode=""`. Assert envelope keys present in `data`.
3. Type spot-checks: `effects_applied: int`, `mode: str`, `snapshot_id: str`, `required_producers_hint: list`.

## Expected Results
- Signature + envelope match.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_apply_envelope -v`

## Pass / Fail Criteria
- **Pass:** Match.
- **Fail:** Otherwise.
