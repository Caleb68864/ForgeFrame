---
scenario_id: "IO-02"
title: "Preset model field shape and defaults"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - structural
---

# Scenario IO-02: Preset Pydantic field shape

## Description
Verifies `[STRUCTURAL]` -- `Preset` exposes the spec's required fields, types, and defaults.

## Preconditions
- Module importable.

## Steps
1. Inspect `Preset.model_fields` keys.
2. Assert keys equal `{name, version, created_at, updated_at, created_by, tags, description, source, effects, apply_hints}`.
3. Assert defaults: `version == 1`, `tags == ()`, `description == ""`, `source is None`, `apply_hints == ApplyHints()`.
4. Construct minimal valid `Preset(name="x", created_at=..., updated_at=..., created_by="t", effects=())` and assert it validates.
5. Assert `Preset.model_config` has `extra="ignore"` (forward-compat from Edge Cases).

## Expected Results
- Field set, types, defaults match spec exactly.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_preset_fields -v`

## Pass / Fail Criteria
- **Pass:** All field assertions hold.
- **Fail:** Any field missing, wrong type, or wrong default.
