---
scenario_id: "SS1-04"
title: "ParamDef has documented field set"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, structural]
---

# Scenario SS1-04: ParamDef has documented field set

## Description
Verifies `[STRUCTURAL]` `ParamDef` is a frozen slots dataclass with the documented fields and types: `name, display_name, type (ParamType), default (str|None), min (float|None), max (float|None), decimals (int|None), values (tuple[str,...]), value_labels (tuple[str,...]), keyframable (bool)`.

## Preconditions
- Parser module importable.

## Steps
1. Import `ParamDef, ParamType`.
2. Confirm dataclass + frozen + `__slots__`.
3. Assert field-name set matches the 10 documented names.
4. For each field, inspect `f.type` annotation and assert it matches the spec.

## Expected Results
- Exact field/type contract met.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_paramdef_shape -v`

## Pass / Fail Criteria
- **Pass:** Structural asserts succeed.
- **Fail:** Field/type mismatch.
