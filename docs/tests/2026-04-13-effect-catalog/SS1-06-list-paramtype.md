---
scenario_id: "SS1-06"
title: "parse_param on type=list extracts paramlist + paramlistdisplay"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-06: parse_param on type=list extracts paramlist + paramlistdisplay

## Description
Verifies `[BEHAVIORAL]` list-type parameter parsing: `paramlist="0;1"` + `<paramlistdisplay>Average,Maximum</paramlistdisplay>` produces `values=("0","1")` and `value_labels=("Average","Maximum")`.

## Preconditions
- Fixture XML containing the `av.link` `<parameter type="list">` element.

## Steps
1. Parse the XML, locate the `av.link` ParamDef.
2. Assert `pd.type == ParamType.LIST`.
3. Assert `pd.values == ("0", "1")`.
4. Assert `pd.value_labels == ("Average", "Maximum")`.
5. Assert `pd.keyframable is False`.

## Expected Results
- Tuple values + labels correctly split.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_param_list -v`

## Pass / Fail Criteria
- **Pass:** All asserts succeed.
- **Fail:** Wrong split or missing labels.
