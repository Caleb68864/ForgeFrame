---
scenario_id: "INT-03"
title: "effect_keyframe_set_rect end-to-end write + re-parse"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - behavioral
  - sequential
---

# Scenario INT-03: End-to-end rect keyframe write + re-parse

## Description
Verifies [BEHAVIORAL] Sub-Spec 4 -- against the fixture project, calling `effect_keyframe_set_rect` writes the expected keyframe string into `<property name="rect">` and re-parsing the project yields an identical keyframe list.

Note: sequential because it mutates the fixture workspace state (auto-snapshot occurs).

## Preconditions
- Fixture `tests/integration/fixtures/keyframe_project.kdenlive` present with a `transform` filter on clip `(2, 0)`.
- Fresh temp workspace created; fixture copied into it.

## Steps
1. Create a temp workspace from the fixture.
2. Invoke `effect_keyframe_set_rect(workspace=<temp>, track=2, clip=0, effect_index=0, property="rect", keyframes=[{"frame":0,"value":[0,0,1920,1080],"easing":"linear"},{"seconds":2,"value":[100,50,1920,1080,0.5],"easing":"ease_in_out"}], mode="replace")`.
3. Re-read the written `.kdenlive` from disk.
4. Locate the `<property name="rect">` text under the transform filter on clip `(2, 0)`.
5. Parse the text via `parse_keyframe_string("rect", text)`.
6. Assert the parsed list matches the input `keyframes` (with 4-tuple normalized to 5-tuple with opacity=1 on the first entry, and ease_in_out resolved to `i` or the family-default operator).
7. Assert the raw text equals `"00:00:00.000=0 0 1920 1080 1;00:00:02.000i=100 50 1920 1080 0.5"` (assuming workspace ease_family=cubic).

## Expected Results
- XML written correctly.
- Round-trip parse-then-compare succeeds.
- Snapshot id is present in the tool's return dict.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_set_rect_end_to_end -v`

## Pass / Fail Criteria
- **Pass:** Exact XML + round-trip equality.
- **Fail:** XML drift, missing/wrong snapshot id, or parse mismatch.
