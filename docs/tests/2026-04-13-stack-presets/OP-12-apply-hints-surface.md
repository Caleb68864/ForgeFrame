---
scenario_id: "OP-12"
title: "apply_preset response surfaces blend/track/required hints verbatim"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-12: apply_preset response surfaces hints

## Description
Verifies `[BEHAVIORAL]` -- response includes `blend_mode_hint`, `track_placement_hint`, `required_producers_hint` taken verbatim from `preset.apply_hints` (no acting on them; hints are metadata for caller).

## Preconditions
- Preset with `apply_hints = ApplyHints(blend_mode="screen", stack_order="append", track_placement="V2", required_producers=("audiofile.wav",))`.

## Steps
1. Call `apply_preset(project, target_ref, preset)`.
2. Assert `response["blend_mode_hint"] == "screen"`.
3. Assert `response["track_placement_hint"] == "V2"`.
4. Assert `response["required_producers_hint"] == ("audiofile.wav",)`.
5. Assert no track movement actually occurred (target clip remains on its original track) and no producer was added to the project.

## Expected Results
- Hints surfaced; no side effects from them.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_apply_hints_surfaced -v`

## Pass / Fail Criteria
- **Pass:** Verbatim hints; no track/producer mutation.
- **Fail:** Otherwise.
