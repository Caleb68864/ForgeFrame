---
scenario_id: "IO-04"
title: "ApplyHints field shape, defaults, and Literal stack_order"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - structural
---

# Scenario IO-04: ApplyHints Pydantic field shape

## Description
Verifies `[STRUCTURAL]` -- `ApplyHints` fields: `blend_mode: str|None = None`, `stack_order: Literal["append","prepend","replace"] = "append"`, `track_placement: str|None = None`, `required_producers: tuple[str, ...] = ()`.

## Preconditions
- Module importable.

## Steps
1. Inspect `ApplyHints.model_fields`.
2. Assert keys equal `{blend_mode, stack_order, track_placement, required_producers}`.
3. Construct `ApplyHints()` and assert defaults: `blend_mode is None`, `stack_order == "append"`, `track_placement is None`, `required_producers == ()`.
4. Attempt `ApplyHints(stack_order="bogus")` -- assert `ValidationError`.
5. Each of `"append"`, `"prepend"`, `"replace"` is accepted.

## Expected Results
- Defaults correct; Literal enforces three valid values.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_apply_hints_fields -v`

## Pass / Fail Criteria
- **Pass:** All assertions hold.
- **Fail:** Any deviation from spec.
