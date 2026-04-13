---
scenario_id: "SR-30"
title: "Malformed JSON / invalid input handling on effects_paste"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - error-path
---

# Scenario SR-30: Invalid input handling on effects_paste

## Description
Verifies `[BEHAVIORAL]` edge cases at the MCP boundary -- malformed JSON, stack dict missing `effects`, invalid mode, and non-existent clip each return an `_err` envelope (no exception escape) with a helpful message.

## Preconditions
- Fresh workspace with fixture.

## Steps
1. `effects_paste(... stack="{not json", mode="append")` -- assert `status="error"` and message references `effects_copy` or JSON parse failure.
2. `effects_paste(... stack=json.dumps({"source_clip":[2,0]}), mode="append")` -- assert `status="error"` and message mentions missing `effects` and points at `effects_copy`.
3. `effects_paste(... stack=json.dumps({"source_clip":[2,0],"effects":[]}), mode="merge")` -- assert `status="error"` listing `append`, `prepend`, `replace`.
4. `effects_copy(... track=99, clip=99)` against a non-existent clip -- assert `status="error"` (wraps `IndexError` from `_iter_clip_filters`).

## Expected Results
- All four invalid inputs produce `_err` envelopes with helpful messages; no uncaught exceptions cross the MCP boundary.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_invalid_inputs -v`

## Pass / Fail Criteria
- **Pass:** Error envelopes returned for each case with helpful messages.
- **Fail:** Exception escapes MCP layer, silent acceptance, or unhelpful message.
