---
scenario_id: "SR-25"
title: "Paste mode=replace clears target's pre-existing filters"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - sequential
---

# Scenario SR-25: MCP paste replace mode

## Description
Verifies `[BEHAVIORAL]` -- via the MCP boundary, `effects_paste(... mode="replace")` clears target's pre-existing filters before inserting source filters.

## Preconditions
- Fresh workspace with fixture.
- Target clip pre-loaded with a known set of filters distinct from source.
- Sequential -- mutates state.

## Steps
1. Use `effect_add` (existing tool) to ensure target clip has, say, 2 distinct filters.
2. `cp = effects_copy(... source_track, source_clip)`; record source filter ids.
3. `pst = effects_paste(... target_track, target_clip, stack=json.dumps(cp.data.stack), mode="replace")`.
4. `post = list_effects(target_track, target_clip)`.
5. Assert `len(post) == cp.data.effect_count`.
6. Assert post filter ids match source ids exactly (no prior target filters remain).

## Expected Results
- Target stack equals source stack post-replace.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_paste_replace -v`

## Pass / Fail Criteria
- **Pass:** Old filters gone; new filters present in correct order.
- **Fail:** Old filters retained or new filters missing.
