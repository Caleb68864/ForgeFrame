---
scenario_id: "EP-03"
title: "composite_set return shape matches spec"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] return shape"]
tags: [test-scenario, mcp, structural, critical]
---

# Scenario EP-03: composite_set return shape matches spec

## Description
Spec Sub-Spec 2: return shape is `{"status","data":{"composition_added": true, "blend_mode": str, "track_a": int, "track_b": int, "snapshot_id": str}}`.

## Preconditions
- Test workspace set up in `tmp_path` (mirror `test_mcp_tools.py` harness).
- Fixture project copied into workspace.

## Steps
1. Use `workspace_create` / existing helper to set up a workspace under `tmp_path`.
2. Copy `sample_tutorial.kdenlive` into the workspace.
3. Call `composite_set(workspace_path=str(tmp_path), project_file="sample_tutorial.kdenlive", track_a=1, track_b=2, start_frame=0, end_frame=60, blend_mode="screen")`.
4. Assert result is a dict.
5. Assert `result["status"] == "ok"` (per `_ok` helper convention in the codebase).
6. Assert `result["data"]["composition_added"] is True`.
7. Assert `result["data"]["blend_mode"] == "screen"`.
8. Assert `result["data"]["track_a"] == 1 and result["data"]["track_b"] == 2`.
9. Assert `isinstance(result["data"]["snapshot_id"], str) and result["data"]["snapshot_id"]`.

## Expected Results
- Return dict exactly matches spec schema.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_composite_set_return_shape -v`

## Pass / Fail Criteria
- **Pass:** All keys/values match.
- **Fail:** Missing key, wrong type, or wrong value.
