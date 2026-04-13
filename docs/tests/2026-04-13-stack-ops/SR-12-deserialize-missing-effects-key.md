---
scenario_id: "SR-12"
title: "deserialize_stack rejects dict missing effects key"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
  - error-path
---

# Scenario SR-12: deserialize_stack input validation

## Description
Verifies `[BEHAVIORAL]` -- `deserialize_stack({})` (or any dict missing `effects`) raises `ValueError` whose message points the caller at `effects_copy` as the expected producer.

## Preconditions
- Pipeline module importable.

## Steps
1. With `pytest.raises(ValueError) as exc`: call `deserialize_stack({})`.
2. Assert `"effects_copy"` substring in `str(exc.value)`.
3. Repeat with `deserialize_stack({"source_clip": [2,0]})` -- still missing `effects`.
4. Assert same error.

## Expected Results
- `ValueError` raised; message includes `effects_copy` as guidance.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_deserialize_missing_key -v`

## Pass / Fail Criteria
- **Pass:** Both raise with effects_copy mentioned.
- **Fail:** Wrong exception or unhelpful message.
