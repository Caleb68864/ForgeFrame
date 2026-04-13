---
scenario_id: "SR-19"
title: "Keyframe animation strings preserved byte-exact through paste"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
  - keyframes
---

# Scenario SR-19: Keyframe byte-exact preservation through serialize/paste

## Description
Verifies `[BEHAVIORAL]` -- a filter carrying an animated keyframe property string survives `serialize_stack` -> JSON round-trip -> `apply_paste` with the keyframe property string preserved byte-for-byte (no whitespace munging, no escape changes, no operator-character loss).

## Preconditions
- Source clip with a transform filter that has a `rect` property containing keyframes (use `effect_keyframe_set_rect` from Spec 1 to seed if needed).
- Target clip empty or with unrelated filters.

## Steps
1. Capture source filter's `rect` property string -- denote `rect_src`.
2. `stack = serialize_stack(project, source_ref)`.
3. `roundtripped = json.loads(json.dumps(stack))`.
4. `apply_paste(project, target_ref, roundtripped, mode="append")`.
5. Re-fetch the pasted filter from target and read its `rect` property -- denote `rect_tgt`.
6. Assert `rect_src == rect_tgt` byte-for-byte (including operator characters, semicolons, time format).

## Expected Results
- Keyframe property strings identical byte-for-byte after paste.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_keyframe_preservation -v`

## Pass / Fail Criteria
- **Pass:** Strings exactly equal.
- **Fail:** Any character difference.
