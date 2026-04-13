---
scenario_id: "INT-07"
title: "Each MCP call creates an auto-snapshot; id returned"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - behavioral
  - sequential
---

# Scenario INT-07: Auto-snapshot id returned per call

## Description
Verifies [STRUCTURAL]+[BEHAVIORAL] Sub-Spec 4 -- every MCP keyframe tool call produces a workspace snapshot per the existing auto-snapshot policy and exposes the snapshot id in the tool's return value.

## Preconditions
- Fresh workspace copy of fixture.
- Existing `snapshot_list` / snapshot registry importable or reachable.

## Steps
1. Query initial snapshot count via `snapshot_list` (or equivalent).
2. Invoke `effect_keyframe_set_rect` with a valid payload.
3. Capture the return dict; assert it contains a snapshot id (non-empty string).
4. Query `snapshot_list` again; assert count increased by exactly 1.
5. Assert the returned id matches the newest snapshot in the registry.
6. Repeat for `effect_keyframe_set_scalar` and `effect_keyframe_set_color`; each call produces its own new snapshot with a unique id.

## Expected Results
- One snapshot per MCP call.
- Returned id matches registry.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_auto_snapshot -v`

## Pass / Fail Criteria
- **Pass:** Snapshot created + id returned per call.
- **Fail:** Missing id, missing snapshot, or policy bypassed.
