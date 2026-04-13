---
scenario_id: "SR-23"
title: "MCP effect_chroma_key signature and return shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-3
---

# Scenario SR-23: MCP effect_chroma_key signature and return shape

## Description
Verifies [STRUCTURAL] `effect_chroma_key(workspace_path, project_file, track, clip, color: str = "#00FF00", tolerance: float = 0.15, blend: float = 0.0) -> dict` returns `{"effect_index", "snapshot_id"}`.

## Preconditions
- Workspace fixture ready.

## Steps
1. Inspect signature; assert defaults exactly (`color="#00FF00"`, `tolerance=0.15`, `blend=0.0`).
2. Call with defaults.
3. Assert return keys `effect_index`, `snapshot_id`.

## Expected Results
- Signature defaults match.
- Return shape matches.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_effect_chroma_key_signature -v`

## Pass / Fail Criteria
- **Pass:** signature and return match spec.
- **Fail:** any mismatch.
