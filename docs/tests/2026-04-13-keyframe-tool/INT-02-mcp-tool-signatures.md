---
scenario_id: "INT-02"
title: "MCP tool signatures match spec"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - structural
---

# Scenario INT-02: MCP tool signatures

## Description
Verifies [STRUCTURAL] Sub-Spec 4 -- the registered tools have exactly the signatures the spec mandates.

## Preconditions
- INT-01 passes.

## Steps
1. For each keyframe tool, inspect its MCP input schema (or Python signature). Assert parameters: `workspace: str, track: int, clip: int, effect_index: int, property: str, keyframes: list, mode: Literal["replace","merge"] = "replace"`.
2. Assert the tool's return type is `dict` and the schema documents a snapshot id field.
3. Inspect `effect_find` signature -- assert `(workspace: str, track: int, clip: int, name: str) -> int`.
4. Assert `mode` default is `"replace"` and Literal constrains values.

## Expected Results
- All four signatures match spec byte-for-byte.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_signatures -v`

## Pass / Fail Criteria
- **Pass:** Signatures exact.
- **Fail:** Any drift in names/types/defaults.
