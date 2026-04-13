---
scenario_id: "IO-03"
title: "PresetEffect model field shape and defaults"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - structural
---

# Scenario IO-03: PresetEffect Pydantic field shape

## Description
Verifies `[STRUCTURAL]` -- `PresetEffect` fields per spec: `mlt_service: str`, `kdenlive_id: str = ""`, `xml: str`.

## Preconditions
- Module importable.

## Steps
1. Inspect `PresetEffect.model_fields`.
2. Assert keys equal `{mlt_service, kdenlive_id, xml}`.
3. Assert `kdenlive_id` default is `""`.
4. Assert `mlt_service` and `xml` are required (no default; instantiation without them raises `ValidationError`).

## Expected Results
- Field set, types, defaults match spec exactly.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_preset_effect_fields -v`

## Pass / Fail Criteria
- **Pass:** Field shape matches.
- **Fail:** Any deviation.
