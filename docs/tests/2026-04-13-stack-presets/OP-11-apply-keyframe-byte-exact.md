---
scenario_id: "OP-11"
title: "apply_preset preserves keyframe rect property byte-exact across clips"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
  - keyframes
---

# Scenario OP-11: keyframe byte-exactness through serialize -> save -> load -> apply

## Description
Verifies `[BEHAVIORAL]` -- copy a keyframed `rect` property by serializing source, saving to YAML, loading back, applying to a different clip; assert re-parsed `rect` property on target equals source byte-for-byte.

## Preconditions
- Source clip with a transform/qtblend filter carrying a complex animated `rect` (multi-keyframe with operators).

## Steps
1. Capture source `rect` via `patcher.get_effect_property(project, src_ref, effect_index, "rect")` -> `rect_src`.
2. `preset = serialize_clip_to_preset(project, src_ref, name="kfm")`.
3. `save_preset(preset, ws, scope="workspace")`.
4. `loaded = load_preset("kfm", ws, vault=None)`.
5. `apply_preset(project, target_ref, loaded, mode_override="append")`.
6. Read back `rect_tgt = patcher.get_effect_property(project, target_ref, new_effect_index, "rect")`.
7. Assert `rect_src == rect_tgt`.

## Expected Results
- `rect_tgt` equals `rect_src` byte-for-byte.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_apply_keyframe_byte_exact -v`

## Pass / Fail Criteria
- **Pass:** Byte equality.
- **Fail:** Any difference.
