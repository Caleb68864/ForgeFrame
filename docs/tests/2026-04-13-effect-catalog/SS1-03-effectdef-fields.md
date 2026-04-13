---
scenario_id: "SS1-03"
title: "EffectDef has documented field set"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, structural]
---

# Scenario SS1-03: EffectDef has documented field set

## Description
Verifies `[STRUCTURAL]` `EffectDef` is a frozen dataclass with `slots=True` and exactly the fields: `kdenlive_id, mlt_service, display_name, description, category, params`.

## Preconditions
- Parser module importable.

## Steps
1. Import `EffectDef`.
2. `import dataclasses; assert dataclasses.is_dataclass(EffectDef)`.
3. Assert `EffectDef.__dataclass_params__.frozen is True`.
4. Assert `"__slots__" in EffectDef.__dict__`.
5. Build expected field-name set; assert `{f.name for f in dataclasses.fields(EffectDef)} == expected`.
6. Assert annotation types match spec (`category` annotated as `str`, `params` annotated as `tuple[ParamDef, ...]`).

## Expected Results
- Frozen slots dataclass with exact field set + types.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_effectdef_shape -v`

## Pass / Fail Criteria
- **Pass:** All structural asserts succeed.
- **Fail:** Field mismatch or missing slots/frozen.
