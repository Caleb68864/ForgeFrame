---
scenario_id: "SR-22"
title: "MCP mask_apply signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-22: MCP mask_apply signature and return shape

## Description
Verifies [STRUCTURAL] `mask_apply(workspace_path, project_file, track, clip, mask_effect_index: int, target_effect_index: int) -> dict` returns `{"mask_effect_index","target_effect_index","reordered","snapshot_id"}`.

## Preconditions
- Workspace fixture with a mask and target filter pre-applied.

## Steps
1. Inspect signature; assert parameter names and int types for `mask_effect_index`, `target_effect_index`.
2. Call `mask_apply(..., mask_effect_index=0, target_effect_index=1)`.
3. Assert return keys exactly: `mask_effect_index`, `target_effect_index`, `reordered`, `snapshot_id`.
4. Assert types: int, int, bool, str.

## Expected Results
- Signature matches.
- Return keys and types match.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_mask_apply_signature -v`

## Pass / Fail Criteria
- **Pass:** signature and return shape exactly match.
- **Fail:** missing key or wrong type.
