---
scenario_id: "SS1-14"
title: "Empty <description> yields empty string not None"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, edge-case]
---

# Scenario SS1-14: Empty <description> yields empty string not None

## Description
Verifies edge-case: missing or empty `<description>` produces `description=""`, never None.

## Preconditions
- Fixture variants: one with `<description></description>`, one with no `<description>` element.

## Steps
1. Parse both fixtures.
2. Assert `eff.description == ""` for each.
3. Assert `isinstance(eff.description, str)`.

## Expected Results
- Always a string, possibly empty.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_empty_description -v`

## Pass / Fail Criteria
- **Pass:** Both asserts succeed.
- **Fail:** None or AttributeError.
