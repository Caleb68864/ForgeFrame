---
scenario_id: "EDGE-03"
title: "FPS re-read from project on every call (no caching)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - edge-case
---

# Scenario EDGE-03: FPS re-read per call

## Description
Verifies the "Must Nots: no caching layer for fps" constraint and Requirement 8 -- FPS is read from the `.kdenlive` project profile on every MCP call.

## Preconditions
- Fixture workspace with known fps (e.g., 30 fps).
- Ability to patch/mock the fps-read function to observe call count.

## Steps
1. Monkeypatch/spy the fps-read helper in the patcher or loader.
2. Invoke `effect_keyframe_set_rect` once; assert fps-read was called.
3. Invoke it again with no intervening changes; assert fps-read was called AGAIN (count increments).
4. As an additional probe: change the project profile fps on disk between calls (24 -> 60) and invoke the tool; assert the second call uses the NEW fps for time conversion (e.g., `{"seconds":1}` maps to frame 60, not 24).

## Expected Results
- fps-read invoked per call (no memoization).
- Profile change mid-session picked up.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_fps_no_cache -v`

## Pass / Fail Criteria
- **Pass:** Fresh read every call + profile change respected.
- **Fail:** Cached fps or stale value reused.
