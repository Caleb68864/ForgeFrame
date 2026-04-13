---
scenario_id: "SS1-13"
title: "type=list missing paramlistdisplay falls back to raw values"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, edge-case]
---

# Scenario SS1-13: type=list missing paramlistdisplay falls back to raw values

## Description
Verifies edge-case (spec Edge Cases): when a `<parameter type="list">` lacks `<paramlistdisplay>`, parser uses the raw `paramlist` values for both `values` and `value_labels`.

## Preconditions
- Fixture containing `<parameter type="list" name="mode" paramlist="a;b;c"/>` with no `<paramlistdisplay>` child.

## Steps
1. Parse fixture; locate that ParamDef.
2. Assert `pd.values == ("a", "b", "c")`.
3. Assert `pd.value_labels == ("a", "b", "c")`.

## Expected Results
- Labels mirror values when display is absent.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_list_missing_paramlistdisplay -v`

## Pass / Fail Criteria
- **Pass:** Tuples equal.
- **Fail:** Empty labels or KeyError.
