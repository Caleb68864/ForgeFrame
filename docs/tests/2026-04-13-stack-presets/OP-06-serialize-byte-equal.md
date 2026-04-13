---
scenario_id: "OP-06"
title: "serialize_clip_to_preset 3-filter clip -> 3 PresetEffects byte-equal xml"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
  - keyframes
---

# Scenario OP-06: serialize_clip_to_preset xml byte-equality

## Description
Verifies `[BEHAVIORAL]` -- against a clip with 3 filters, serialization produces 3 `PresetEffect`s whose `xml` equals the source `OpaqueElement.xml_string` byte-for-byte.

## Preconditions
- Fixture project clip with exactly 3 filters (seed via `patcher.insert_effect_xml` if needed).

## Steps
1. Capture source xml strings: `[op.xml_string for op in patcher._iter_clip_filters(project, clip_ref)]`.
2. `preset = serialize_clip_to_preset(project, clip_ref, name="three")`.
3. Assert `len(preset.effects) == 3`.
4. For i in 0..2: assert `preset.effects[i].xml == source_xml[i]` byte-for-byte.

## Expected Results
- Three effects; xml byte-equal.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_serialize_byte_equal -v`

## Pass / Fail Criteria
- **Pass:** All three byte-equal.
- **Fail:** Any difference.
