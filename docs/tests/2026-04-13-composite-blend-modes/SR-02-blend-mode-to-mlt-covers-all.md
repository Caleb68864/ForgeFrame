---
scenario_id: "SR-02"
title: "BLEND_MODE_TO_MLT maps every mode to a non-empty MLT value"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] BLEND_MODE_TO_MLT"]
tags: [test-scenario, pipeline, structural, critical]
---

# Scenario SR-02: BLEND_MODE_TO_MLT maps every mode to a non-empty MLT value

## Description
Validates `BLEND_MODE_TO_MLT: dict[str, str]` has a key for every member of `BLEND_MODES` and no extras, and that every mapped value is a non-empty string. If MLT accepts abstract names verbatim, identity mapping is fine; if not, spec permits explicit overrides (e.g. `destination_in -> dst-in`).

## Preconditions
- SR-01 passes.

## Steps
1. Import `BLEND_MODES` and `BLEND_MODE_TO_MLT` from `workshop_video_brain.edit_mcp.pipelines.compositing`.
2. Assert `set(BLEND_MODE_TO_MLT.keys()) == BLEND_MODES`.
3. For every key/value pair, assert `isinstance(value, str) and value`.
4. Snapshot the mapping (`repr(BLEND_MODE_TO_MLT)`) against a committed inline-expected string to detect silent drift.
5. If any entry is non-identity (key != value), assert the value matches the worker-derived MLT identifier recorded in a module-level comment or constant.

## Expected Results
- Keys exactly match `BLEND_MODES`.
- All values are non-empty strings.
- Mapping matches the committed snapshot.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_blend_mode_to_mlt_coverage -v`

## Pass / Fail Criteria
- **Pass:** Every abstract mode maps to a non-empty MLT value; snapshot matches.
- **Fail:** Missing key, extra key, empty value, or snapshot drift.
