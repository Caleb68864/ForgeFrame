---
scenario_id: "SR-10"
title: "serialize_stack round-trip through deserialize_stack"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
---

# Scenario SR-10: serialize/deserialize round-trip

## Description
Verifies `[BEHAVIORAL]` -- a stack dict from `serialize_stack` survives `json.dumps` -> `json.loads` -> `deserialize_stack` and yields a list of XML strings byte-equal to the source clip's `OpaqueElement.xml_string` values, in original order.

## Preconditions
- Clip with N>=2 filters.

## Steps
1. `stack = serialize_stack(project, (2,0))`.
2. `roundtripped = json.loads(json.dumps(stack))`.
3. `xml_list = deserialize_stack(roundtripped)`.
4. Compare element-wise with the source clip's filter `OpaqueElement.xml_string` list.
5. Assert lengths equal and each string identical (byte-for-byte).

## Expected Results
- Round-trip preserves all filter xml verbatim and in order.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_roundtrip -v`

## Pass / Fail Criteria
- **Pass:** All strings byte-equal and ordered.
- **Fail:** Any mismatch.
