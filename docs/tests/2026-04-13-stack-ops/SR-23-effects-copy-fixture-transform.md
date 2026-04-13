---
scenario_id: "SR-23"
title: "effects_copy on fixture (track=2, clip=0) yields effect_count >= 1, transform first"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
---

# Scenario SR-23: effects_copy fixture sanity

## Description
Verifies `[BEHAVIORAL]` -- against `tests/integration/fixtures/keyframe_project.kdenlive`, calling `effects_copy(track=2, clip=0)` returns `effect_count >= 1` and the first filter has `kdenlive_id="transform"`.

## Preconditions
- Fixture `keyframe_project.kdenlive` present and copied into a temp workspace.

## Steps
1. Set up temp workspace with the fixture.
2. Call `effects_copy(workspace_path, project_file=fixture, track=2, clip=0)`.
3. Assert `result["status"] == "ok"`.
4. Assert `result["data"]["effect_count"] >= 1`.
5. Assert `result["data"]["stack"]["effects"][0]["kdenlive_id"] == "transform"`.

## Expected Results
- Copy succeeds with non-empty stack and transform filter at index 0.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_copy_fixture -v`

## Pass / Fail Criteria
- **Pass:** All assertions pass.
- **Fail:** Wrong count or missing transform.
