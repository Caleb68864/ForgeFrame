---
scenario_id: "SR-24"
title: "MCP effect_chroma_key_advanced signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-24: MCP effect_chroma_key_advanced signature and return shape

## Description
Verifies [STRUCTURAL] `effect_chroma_key_advanced(workspace_path, project_file, track, clip, color: str, tolerance_near: float, tolerance_far: float, edge_smooth: float = 0.0, spill_suppression: float = 0.0) -> dict`.

## Preconditions
- Workspace fixture ready.

## Steps
1. Inspect signature; assert required positional `color`, `tolerance_near`, `tolerance_far`, and defaults `edge_smooth=0.0`, `spill_suppression=0.0`.
2. Call with `color="#00FF00", tolerance_near=0.1, tolerance_far=0.3`.
3. Assert return keys include `effect_index` and `snapshot_id`.

## Expected Results
- Signature defaults match.
- Required params enforced.
- Return shape consistent.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_effect_chroma_key_advanced_signature -v`

## Pass / Fail Criteria
- **Pass:** all assertions hold.
- **Fail:** any mismatch.
