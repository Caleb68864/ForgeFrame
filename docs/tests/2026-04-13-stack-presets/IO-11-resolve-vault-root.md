---
scenario_id: "IO-11"
title: "resolve_vault_root precedence: project json -> forge.json -> None"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-11: resolve_vault_root precedence

## Description
Verifies `[BEHAVIORAL]` -- `resolve_vault_root(project_json_path, forge_config_path)` returns the first available of `forge-project.json.vault_root`, then `~/.claude/forge.json.personal_vault`, else `None`.

## Preconditions
- `tmp_path` workspace.

## Steps
1. **Both set:** project json `{"vault_root": "/A"}`, forge config `{"personal_vault": "/B"}`. Assert returns `Path("/A")`.
2. **Only forge config set:** project json `{}` (no `vault_root`); forge config `{"personal_vault": "/B"}`. Assert returns `Path("/B")`.
3. **Neither set:** both empty. Assert returns `None`.
4. **Project json missing file:** assert function does not raise; falls through to forge config.
5. **Forge config missing file:** assert returns `None` (when project json also empty).
6. Vault path is expanded/resolved to absolute (per Edge Case: spaces, relative path, `~`).

## Expected Results
- Precedence as documented; absolute resolution.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_resolve_vault_root -v`

## Pass / Fail Criteria
- **Pass:** All five branches behave as specified.
- **Fail:** Any branch wrong.
