---
scenario_id: "MCP-09"
title: "End-to-end preset -> apply -> list_effects matches; reparse preserves keyframes byte-exact"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - integration
  - keyframes
sequential: true
---

# Scenario MCP-09: MCP end-to-end with keyframe preservation

## Description
Verifies `[BEHAVIORAL]`/`[INTEGRATION]` -- save a preset from a keyframed source clip via MCP, apply it to a target clip via MCP, verify filter count via `patcher.list_effects`; reload the project from disk and assert the keyframed `rect` property on the target clip equals the source byte-for-byte.

## Preconditions
- Fixture copied; source clip has a keyframed transform filter.

## Steps
1. Capture `rect_src` from source clip via `patcher.get_effect_property`.
2. `effect_stack_preset(track=src_track, clip=src_clip, name="kfm-e2e")`.
3. `effect_stack_apply(track=tgt_track, clip=tgt_clip, name="kfm-e2e", mode="")`.
4. Assert `len(patcher.list_effects(project, tgt_ref)) == response.data.effects_applied`.
5. Reload the project file from disk into a fresh `Project` instance.
6. Re-read `rect_tgt` from the reloaded target clip.
7. Assert `rect_src == rect_tgt`.

## Expected Results
- Filter count matches; keyframe byte-equal post-disk-roundtrip.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_e2e_keyframe_preservation -v`

## Pass / Fail Criteria
- **Pass:** All assertions hold.
- **Fail:** Otherwise.
