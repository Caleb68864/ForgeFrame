---
scenario_id: "SR-21"
title: "MCP mask_set_shape signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-21: MCP mask_set_shape signature and return shape

## Description
Verifies [STRUCTURAL] `mask_set_shape(workspace_path, project_file, track, clip, shape: str, bounds: str = "", points: str = "", feather: int = 0, alpha_operation: str = "write_on_clear") -> dict` returns the same shape as `mask_set`.

## Preconditions
- Workspace fixture ready.

## Steps
1. Inspect signature — assert parameter names, defaults (`bounds=""`, `points=""`, `feather=0`, `alpha_operation="write_on_clear"`).
2. Call with `shape="rect"`, `bounds="[0.1,0.1,0.5,0.5]"`.
3. Assert return shape: `{"status", "data": {"effect_index": int, "type": str, "snapshot_id": str}}`.

## Expected Results
- Signature and defaults match spec.
- Return shape identical to `mask_set`.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_mask_set_shape_signature -v`

## Pass / Fail Criteria
- **Pass:** signature, defaults, and return match.
- **Fail:** any mismatch.
