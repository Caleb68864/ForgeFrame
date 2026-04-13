---
scenario_id: "OP-02"
title: "serialize_clip_to_preset signature returns a Preset"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - structural
---

# Scenario OP-02: serialize_clip_to_preset signature

## Description
Verifies `[STRUCTURAL]` -- function accepts `(project, clip_ref, name, description="", tags=(), created_by="effect_stack_preset")` and returns a `Preset`.

## Preconditions
- Use the `keyframe_project.kdenlive` fixture loaded via existing helpers.

## Steps
1. Inspect `inspect.signature(serialize_clip_to_preset)`; assert parameter names and defaults match spec exactly.
2. Call with a real clip ref. Assert return type `isinstance(result, Preset)`.

## Expected Results
- Signature matches; returns Preset.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_serialize_signature -v`

## Pass / Fail Criteria
- **Pass:** Signature and type match.
- **Fail:** Otherwise.
