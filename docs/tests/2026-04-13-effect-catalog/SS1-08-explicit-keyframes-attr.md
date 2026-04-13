---
scenario_id: "SS1-08"
title: "parse_param honours explicit keyframes=\"1\" attr"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-08: parse_param honours explicit keyframes="1" attr

## Description
Verifies `[BEHAVIORAL]` rule: a non-animating type (e.g. `constant`) with `keyframes="1"` attr yields `keyframable=True`.

## Preconditions
- Fixture XML with `<parameter type="constant" name="x" keyframes="1" ...>`.

## Steps
1. Parse fixture; locate that ParamDef.
2. Assert `pd.type == ParamType.CONSTANT`.
3. Assert `pd.keyframable is True`.

## Expected Results
- Explicit attribute overrides type-based default.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_param_explicit_keyframes_attr -v`

## Pass / Fail Criteria
- **Pass:** Assert succeeds.
- **Fail:** keyframable False.
