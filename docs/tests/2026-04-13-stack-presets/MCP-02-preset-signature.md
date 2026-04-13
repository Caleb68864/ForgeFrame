---
scenario_id: "MCP-02"
title: "effect_stack_preset signature and return envelope"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario MCP-02: effect_stack_preset envelope shape

## Description
Verifies `[STRUCTURAL]` -- `effect_stack_preset(workspace_path, project_file, track, clip, name, description="", tags: str = "", apply_hints: str = "")` returns `{"status","data":{"path":str,"effect_count":int,"scope":"workspace"}}`. `tags` and `apply_hints` are JSON-encoded strings.

## Preconditions
- Fixture project with at least one filtered clip.

## Steps
1. Inspect `inspect.signature(effect_stack_preset)`; assert parameter names and defaults match exactly.
2. Call with valid args (`tags='["foo","bar"]'`, `apply_hints='{"stack_order":"append"}'`).
3. Assert response keys: top-level `status` and `data`; data has `path` (str), `effect_count` (int), `scope == "workspace"`.

## Expected Results
- Signature and envelope match.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_preset_envelope -v`

## Pass / Fail Criteria
- **Pass:** Match.
- **Fail:** Otherwise.
