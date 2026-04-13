---
scenario_id: "IO-08"
title: "load_preset missing in both tiers raises FileNotFoundError listing both paths"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-08: load_preset not found

## Description
Verifies `[BEHAVIORAL]` -- when the named preset is absent from both workspace and vault, `load_preset` raises `FileNotFoundError` whose message names both searched paths.

## Preconditions
- Empty `tmp_path` workspace and vault roots.

## Steps
1. Call `load_preset("ghost", workspace_root=ws, vault_root=vault)` inside `pytest.raises(FileNotFoundError)`.
2. Assert the exception message contains the workspace path string `<ws>/stacks/ghost.yaml` and the vault path string `<vault>/patterns/effect-stacks/ghost.md`.

## Expected Results
- Exception text includes both candidate paths verbatim (or unambiguously).

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_load_missing_lists_paths -v`

## Pass / Fail Criteria
- **Pass:** FileNotFoundError raised with both paths in message.
- **Fail:** Different exception or paths missing.
