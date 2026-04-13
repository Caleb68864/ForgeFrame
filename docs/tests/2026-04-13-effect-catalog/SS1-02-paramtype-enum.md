---
scenario_id: "SS1-02"
title: "ParamType enum covers all 16 known Kdenlive types"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, structural]
---

# Scenario SS1-02: ParamType enum covers all 16 known Kdenlive types

## Description
Verifies `[STRUCTURAL]` enum membership: `CONSTANT, DOUBLE, INTEGER, BOOL, SWITCH, COLOR, KEYFRAME, ANIMATED, GEOMETRY, LIST, FIXED, POSITION, URL, STRING, READONLY, HIDDEN`.

## Preconditions
- Parser module importable.

## Steps
1. Import `ParamType` from `effect_catalog_gen`.
2. Build expected set of 16 names.
3. Assert `{m.name for m in ParamType} == expected`.
4. Assert each enum value's `.value` is the lowercase XML string (e.g. `ParamType.CONSTANT.value == "constant"`).

## Expected Results
- Exactly 16 members, names + values match Kdenlive XML strings.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_paramtype_enum -v`

## Pass / Fail Criteria
- **Pass:** Set equality succeeds.
- **Fail:** Missing/extra members or wrong `.value`.
