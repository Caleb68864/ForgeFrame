---
scenario_id: "PAT-02"
title: "get_effect_property returns existing rect string"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario PAT-02: get_effect_property returns existing rect string

## Description
Verifies [BEHAVIORAL] Sub-Spec 1 -- reads an existing rect property from a transform filter on a fixture clip.

## Preconditions
- Fixture `.kdenlive` project loaded with a `transform` filter on clip (track=2, index=0) whose `rect` property has a known string value.
- Patcher instance constructed against the fixture project tree.

## Steps
1. Load the fixture project via the existing parser.
2. Construct the patcher.
3. Call `patcher.get_effect_property((2, 0), 0, "rect")`.
4. Compare the returned string to the known fixture value.

## Expected Results
- Return value equals the exact rect string stored on the filter's `<property name="rect">` element.
- Type is `str`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_effect_properties.py::test_get_rect -v`

## Pass / Fail Criteria
- **Pass:** Returned string matches fixture exactly.
- **Fail:** Mismatch, wrong type, or exception.
