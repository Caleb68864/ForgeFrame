---
scenario_id: "PAT-04"
title: "list_effects returns filters in stack order with properties"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario PAT-04: list_effects returns filters in stack order with properties

## Description
Verifies [BEHAVIORAL] Sub-Spec 1 -- `list_effects` returns an ordered list of dicts with `index`, `mlt_service`, `kdenlive_id`, and `properties`.

## Preconditions
- Fixture clip has at least two stacked filters in a known order (e.g., `transform` then `brightness`).

## Steps
1. Call `patcher.list_effects((2, 0))`.
2. Assert return type is `list[dict]`.
3. Assert each entry contains keys `index`, `mlt_service`, `kdenlive_id`, `properties`.
4. Assert `index` values are sequential starting at `0`.
5. Assert order matches document order of the `<filter>` children.
6. Assert `properties` is a dict mapping property name to string value.

## Expected Results
- List length matches number of filters on the clip.
- Entries in XML document order.
- `properties` dict captures all `<property>` children.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_effect_properties.py::test_list_effects_order -v`

## Pass / Fail Criteria
- **Pass:** Order, keys, and property contents all correct.
- **Fail:** Wrong order, missing keys, or missing/extra properties.
