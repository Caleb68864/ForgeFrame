---
scenario_id: "SR-28"
title: "Paste rewrites track= / clip_index= in written .kdenlive XML"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - sequential
---

# Scenario SR-28: Attribute rewrite verified by re-parsing project

## Description
Verifies `[BEHAVIORAL]` -- after `effects_paste`, re-parsing the saved `.kdenlive` file shows pasted filters carry the target clip's `track=` / `clip_index=` attribute values.

## Preconditions
- Fresh workspace with fixture.
- Source clip (2,0) and target clip (3,1) (or any other distinct ref).
- Sequential.

## Steps
1. `cp = effects_copy(... 2, 0)`.
2. `effects_paste(... 3, 1, stack=json.dumps(cp.data.stack), mode="append")`.
3. Re-open the on-disk `.kdenlive` file from a fresh parser invocation (do NOT reuse the in-memory project object).
4. Locate target clip (3,1) filters; for each pasted filter, read `track=` and `clip_index=` attributes from the XML.
5. Assert all pasted filters report `track="3"` and `clip_index="1"`.
6. Confirm source clip (2,0) filters are unchanged.

## Expected Results
- On-disk XML reflects rewritten attributes; round-trip safe.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_attr_rewrite_on_disk -v`

## Pass / Fail Criteria
- **Pass:** Re-parse confirms attributes updated.
- **Fail:** Source attributes leaked into target on disk.
