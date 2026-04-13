---
scenario_id: "SR-22"
title: "MCP return envelopes match documented shapes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario SR-22: MCP return envelope shapes

## Description
Verifies `[STRUCTURAL]` -- each tool's return dict matches the documented shape:
- `effects_copy`: `{"status","data":{"stack":{...},"effect_count":int}}`
- `effects_paste`: `{"status","data":{"effects_pasted":int,"mode":str,"snapshot_id":str}}`
- `effect_reorder`: `{"status","data":{"from_index":int,"to_index":int,"snapshot_id":str}}`

## Preconditions
- Working copy of `keyframe_project.kdenlive` in a temp workspace.

## Steps
1. Call `effects_copy(workspace_path, project_file, track=2, clip=0)`; assert `status == "ok"` and `data` keys exact.
2. Call `effects_paste(... stack=<json>, mode="append")`; assert keys and types of `data.effects_pasted`, `data.mode`, `data.snapshot_id`.
3. Call `effect_reorder(... from_index=0, to_index=1)`; assert `data.from_index`, `data.to_index`, `data.snapshot_id` present and typed correctly.

## Expected Results
- All three envelopes exactly match documented shape with correct types.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_envelopes -v`

## Pass / Fail Criteria
- **Pass:** Shapes/types match exactly.
- **Fail:** Missing key, wrong type, or extra unexpected keys.
