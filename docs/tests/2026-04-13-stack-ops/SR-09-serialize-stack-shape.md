---
scenario_id: "SR-09"
title: "serialize_stack returns canonical dict shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - structural
  - behavioral
---

# Scenario SR-09: serialize_stack canonical shape

## Description
Verifies `[STRUCTURAL]`/`[BEHAVIORAL]` -- on a 3-filter clip, `serialize_stack` returns a dict with `source_clip: [track, clip]`, `effects` length 3, each effect dict containing `xml`, `kdenlive_id`, and `mlt_service` keys; and the dict is JSON-serializable.

## Preconditions
- Fixture clip (2,0) with at least 3 filters.

## Steps
1. Call `serialize_stack(project, (2,0))`.
2. Assert returned dict has keys `{"source_clip", "effects"}`.
3. Assert `source_clip == [2, 0]` (list, not tuple, for JSON compatibility).
4. Assert `len(effects) == 3`.
5. For each effect dict, assert keys `{"xml", "kdenlive_id", "mlt_service"}` present.
6. Assert each `effect["xml"]` equals the corresponding `OpaqueElement.xml_string` byte-for-byte.
7. Assert `json.dumps(stack)` succeeds without TypeError.

## Expected Results
- Dict shape matches contract exactly.
- All filter xml preserved verbatim.
- JSON-serializable.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_serialize_shape -v`

## Pass / Fail Criteria
- **Pass:** Shape, content, and JSON round-trip pass.
- **Fail:** Missing keys, wrong types, or non-JSON content.
