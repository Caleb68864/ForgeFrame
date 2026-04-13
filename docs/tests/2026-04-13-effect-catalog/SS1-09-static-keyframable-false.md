---
scenario_id: "SS1-09"
title: "parse_param defaults keyframable=False for static types"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-09: parse_param defaults keyframable=False for static types

## Description
Verifies `[BEHAVIORAL]` rule: type not in animating-set AND no `keyframes` attr -> `keyframable=False`.

## Preconditions
- Fixture XML with `<parameter type="bool" ...>` and `<parameter type="list" ...>` neither carrying `keyframes`.

## Steps
1. Parse fixture; locate both ParamDefs.
2. Assert `pd.keyframable is False` for each.

## Expected Results
- Static params correctly flagged non-keyframable.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_param_static_keyframable_false -v`

## Pass / Fail Criteria
- **Pass:** Both asserts succeed.
- **Fail:** Either returns True.
