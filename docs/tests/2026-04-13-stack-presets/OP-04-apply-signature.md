---
scenario_id: "OP-04"
title: "apply_preset returns documented dict shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - structural
---

# Scenario OP-04: apply_preset return shape

## Description
Verifies `[STRUCTURAL]` -- `apply_preset(project, target_clip_ref, preset, mode_override=None)` returns a dict with keys `effects_applied`, `mode`, `blend_mode_hint`, `track_placement_hint`, `required_producers_hint`.

## Preconditions
- Fixture project loaded; a valid in-memory preset constructed (does not need to be saved).

## Steps
1. Call `apply_preset(project, target_ref, preset)`.
2. Assert returned dict keys are exactly the documented set.
3. Assert types: `effects_applied: int`, `mode: str`, `blend_mode_hint: str|None`, `track_placement_hint: str|None`, `required_producers_hint: tuple` (or list per implementation -- spec says tuple).

## Expected Results
- Return shape matches spec.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_apply_signature -v`

## Pass / Fail Criteria
- **Pass:** All keys + types correct.
- **Fail:** Otherwise.
