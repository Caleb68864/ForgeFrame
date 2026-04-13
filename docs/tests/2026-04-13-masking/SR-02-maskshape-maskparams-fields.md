---
scenario_id: "SR-02"
title: "MaskShape and MaskParams Pydantic fields and defaults"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - sub-spec-1
---

# Scenario SR-02: MaskShape and MaskParams Pydantic fields and defaults

## Description
Verifies the [STRUCTURAL] requirements that `MaskParams` and `MaskShape` are Pydantic models with the exact fields, types, and defaults specified in Sub-Spec 1.

## Preconditions
- `masking` module importable (SR-01 passes)

## Steps
1. Construct `MaskParams()` with no args; inspect field defaults.
2. Construct `MaskShape()` with no args; inspect field defaults.
3. Confirm `MaskParams` fields: `points`, `feather=0`, `passes=1`, `alpha_operation="write_on_clear"`, `spline_is_open=False`.
4. Confirm `MaskShape` fields: `kind` (Literal rect|ellipse|polygon), `bounds=(0,0,1,1)`, `points=()`, `sample_count=32`.
5. Verify `alpha_operation` only accepts allowed Literal values by constructing `MaskParams(points=((0,0),), alpha_operation="bogus")` and asserting `ValidationError`.
6. Verify `kind` only accepts `rect`/`ellipse`/`polygon`.

## Expected Results
- All listed fields and defaults match spec exactly.
- Invalid Literal values raise `pydantic.ValidationError`.
- `points` tuple type accepts tuple of (float, float) tuples.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_maskparams_fields tests/unit/test_masking_pipeline.py::test_maskshape_fields -v`

## Pass / Fail Criteria
- **Pass:** defaults and Literal enforcement match spec.
- **Fail:** any default wrong, any field missing, or Literals not enforced.
