---
scenario_id: "IO-12"
title: "YAML round-trip preserves effects.xml byte-identical"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
  - keyframes
---

# Scenario IO-12: YAML round-trip byte-exactness

## Description
Verifies `[BEHAVIORAL]` -- saving a preset then loading returns byte-identical effect XML strings (no whitespace munging, no entity escapes mutated, no quote rewrites). Critical for downstream keyframe preservation.

## Preconditions
- Construct `Preset` with at least one `PresetEffect` whose `xml` contains a real Kdenlive `<filter>` block including a keyframed `rect` property string with semicolons, equals signs, and double quotes.

## Steps
1. Build preset with `xml_src` containing a complex MLT filter snippet (multi-line, animated `rect="0=100 200 300 400 1.0;25=150 250 300 400 1.0"`).
2. `save_preset(preset, workspace_root=tmp, scope="workspace")`.
3. `loaded = load_preset(preset.name, workspace_root=tmp, vault_root=None)`.
4. Assert `loaded.effects[0].xml == xml_src` (Python `==` byte-equal).
5. Assert all other fields round-trip equal (`name`, `version`, `created_by`, `tags`, `description`, `apply_hints`).

## Expected Results
- `xml` byte-identical; full preset deep-equal except for derived timestamps if any.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_yaml_roundtrip_byte_exact -v`

## Pass / Fail Criteria
- **Pass:** xml byte-equal post-roundtrip.
- **Fail:** Any character difference.
