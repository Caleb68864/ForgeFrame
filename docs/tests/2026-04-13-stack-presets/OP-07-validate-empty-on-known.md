---
scenario_id: "OP-07"
title: "validate_against_catalog returns [] when all services known"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-07: validate_against_catalog all-known

## Description
Verifies `[BEHAVIORAL]` -- a preset whose every `PresetEffect.mlt_service` exists in `effect_catalog.find_by_service` produces `[]` (no warnings) and does not raise even with `strict=True`.

## Preconditions
- A preset built from real catalog services (e.g., `frei0r.bw0r`, `qtblend`, `avfilter.fade`).

## Steps
1. Build preset with services known to `effect_catalog.CATALOG`.
2. Call `validate_against_catalog(preset, strict=False)` -- assert returns `[]`.
3. Call `validate_against_catalog(preset, strict=True)` -- assert returns `[]` (does not raise).

## Expected Results
- Empty list both modes; no raise.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_validate_all_known -v`

## Pass / Fail Criteria
- **Pass:** Empty list returned; no raise.
- **Fail:** Otherwise.
