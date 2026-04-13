---
scenario_id: "SS1-07"
title: "parse_param on type=animated forces keyframable=True"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-07: parse_param on type=animated forces keyframable=True

## Description
Verifies `[BEHAVIORAL]` keyframable inference rule: `type` in `{keyframe, animated, geometry}` forces `keyframable=True` regardless of `keyframes` attribute.

## Preconditions
- Fixture XML with `<parameter type="animated" name="value" ...>` (no `keyframes` attr).

## Steps
1. Parse fixture; locate the animated ParamDef.
2. Assert `pd.type == ParamType.ANIMATED`.
3. Assert `pd.keyframable is True`.
4. Repeat assertion for a `type="keyframe"` and `type="geometry"` parameter in the same fixture.

## Expected Results
- All three "animating" types yield `keyframable=True`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_param_animated_forces_keyframable -v`

## Pass / Fail Criteria
- **Pass:** All three keyframable asserts succeed.
- **Fail:** Any returns False.
