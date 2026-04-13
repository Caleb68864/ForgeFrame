---
scenario_id: "IO-06"
title: "save_preset(scope=vault) writes markdown with frontmatter + body"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-06: save_preset to vault

## Description
Verifies `[BEHAVIORAL]` -- vault save writes `<vault_root>/patterns/effect-stacks/<name>.md` with YAML frontmatter and an auto-generated body.

## Preconditions
- `tmp_path` vault root with no `patterns/effect-stacks/`.
- A constructed `Preset` with description and tags populated.

## Steps
1. Call `save_preset(preset, workspace_root=None, vault_root=tmp_vault, scope="vault")`.
2. Assert `<tmp_vault>/patterns/effect-stacks/<name>.md` exists.
3. Read file; split on `---` fences; assert valid YAML frontmatter parses (`yaml.safe_load`).
4. Assert body section contains the preset name as an H1 or H2 header and a description line.

## Expected Results
- File at documented path; frontmatter parses; body present.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_save_vault -v`

## Pass / Fail Criteria
- **Pass:** File exists with parseable frontmatter and a body.
- **Fail:** Missing file, malformed frontmatter, or empty body.
