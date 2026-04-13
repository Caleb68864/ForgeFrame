---
scenario_id: "SR-01"
title: "BLEND_MODES frozenset contains exactly 11 named modes"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] BLEND_MODES"]
tags: [test-scenario, pipeline, structural]
---

# Scenario SR-01: BLEND_MODES frozenset contains exactly 11 named modes

## Description
Validates the public `BLEND_MODES` export from `pipelines.compositing` is a `frozenset[str]` containing exactly the 11 modes named in the spec. This is the gatekeeping set used for validation everywhere else.

## Preconditions
- Spec 6 Sub-Spec 1 implementation merged.
- `uv sync` done.

## Steps
1. In `tests/unit/test_compositing_blend_modes.py`, import `BLEND_MODES` from `workshop_video_brain.edit_mcp.pipelines.compositing`.
2. Assert `isinstance(BLEND_MODES, frozenset)`.
3. Assert every element is a `str`.
4. Assert `BLEND_MODES == {"cairoblend","screen","lighten","darken","multiply","add","subtract","overlay","destination_in","destination_out","source_over"}`.
5. Assert `len(BLEND_MODES) == 11`.

## Expected Results
- Import succeeds.
- `BLEND_MODES` is a `frozenset[str]`.
- Set equality holds exactly (no extras, no missing).
- Length is 11.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_blend_modes_set -v`

## Pass / Fail Criteria
- **Pass:** Assertions pass; any extra/missing mode fails the set equality.
- **Fail:** Import error, wrong type, or set mismatch.
