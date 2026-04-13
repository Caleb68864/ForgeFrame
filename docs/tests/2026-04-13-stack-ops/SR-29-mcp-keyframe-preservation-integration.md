---
scenario_id: "SR-29"
title: "Keyframe preservation through MCP layer (animated transform copy/paste)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - keyframes
  - sequential
---

# Scenario SR-29: Keyframe preservation through MCP layer

## Description
Verifies `[INTEGRATION]` criterion -- copy a clip with a keyframed transform effect (seeded via `effect_keyframe_set_rect`), paste to another clip via the MCP tools, re-parse the project from disk, and assert the pasted filter's `rect` property string matches the source's byte-for-byte.

## Preconditions
- Fresh workspace with fixture.
- Source clip (2,0) animated via `effect_keyframe_set_rect` with a known keyframe schedule.
- Target clip (3,1) free of conflicting filters.
- Sequential.

## Steps
1. Call `effect_keyframe_set_rect(... 2, 0, ...)` to seed an animated `rect` on the transform filter of the source clip.
2. Re-parse and capture `rect_src` (the property string on source's transform filter).
3. `cp = effects_copy(... 2, 0)`.
4. `effects_paste(... 3, 1, stack=json.dumps(cp.data.stack), mode="append")`.
5. Re-parse `.kdenlive` file from disk (fresh parser).
6. Locate the pasted transform filter on (3,1) and read its `rect` property -- `rect_tgt`.
7. Assert `rect_src == rect_tgt` byte-for-byte (operators, time format, semicolons, escape characters).

## Expected Results
- Keyframe property strings identical between source and pasted target after MCP round-trip.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_keyframe_preservation -v`

## Pass / Fail Criteria
- **Pass:** Byte-equal `rect` strings.
- **Fail:** Any character difference, missing filter, or parse failure.
