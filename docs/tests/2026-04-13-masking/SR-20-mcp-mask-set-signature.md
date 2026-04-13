---
scenario_id: "SR-20"
title: "MCP mask_set signature, params JSON, return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-20: MCP mask_set signature, params JSON, return shape

## Description
Verifies [STRUCTURAL] that `mask_set(workspace_path, project_file, track, clip, type: str, params: str) -> dict` with JSON-encoded params returns `{"status","data":{"effect_index":int,"type":str,"snapshot_id":str}}`.

## Preconditions
- Minimal workspace/project fixture available.

## Steps
1. Inspect `mask_set` signature via `inspect.signature`; assert parameter names and types match.
2. Call `mask_set(workspace_path, project_file, track=2, clip=0, type="rotoscoping", params='{"points": [[0,0],[1,0],[1,1],[0,1]]}')`.
3. Assert return top-level keys: `status`, `data`.
4. Assert `data` contains `effect_index` (int), `type` ("rotoscoping"), `snapshot_id` (str).

## Expected Results
- Signature matches exactly.
- Return shape matches spec.
- `effect_index >= 0`, `snapshot_id` non-empty.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_mask_set_signature_and_return -v`

## Pass / Fail Criteria
- **Pass:** signature and return shape exactly match.
- **Fail:** missing key or wrong type.
