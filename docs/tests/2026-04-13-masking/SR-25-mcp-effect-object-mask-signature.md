---
scenario_id: "SR-25"
title: "MCP effect_object_mask signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-25: MCP effect_object_mask signature and return shape

## Description
Verifies [STRUCTURAL] `effect_object_mask(workspace_path, project_file, track, clip, enabled: bool = True, threshold: float = 0.5) -> dict`.

## Preconditions
- Workspace fixture ready; object_mask effect available in catalog.

## Steps
1. Inspect signature; assert defaults `enabled=True`, `threshold=0.5`.
2. Call with defaults.
3. Assert return keys include `effect_index` and `snapshot_id`.

## Expected Results
- Signature defaults match.
- Return shape consistent.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_effect_object_mask_signature -v`

## Pass / Fail Criteria
- **Pass:** signature and return match.
- **Fail:** any mismatch.
