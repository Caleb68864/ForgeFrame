---
scenario_id: "MCP-15"
title: "effect_stack_promote returns _err when vault root unconfigured"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
---

# Scenario MCP-15: Promote without vault root

## Description
Verifies `[BEHAVIORAL]` -- when neither `forge-project.json.vault_root` nor `~/.claude/forge.json.personal_vault` is set, `effect_stack_promote` returns `_err("Vault root not configured -- set vault_root in forge-project.json or personal_vault in ~/.claude/forge.json")`.

## Preconditions
- Ephemeral HOME with no `~/.claude/forge.json` (or one without `personal_vault`).
- Workspace `forge-project.json` without `vault_root`.
- Workspace preset exists.

## Steps
1. Patch `Path.home()` (or `HOME` env) to a tmp dir with no forge config.
2. Call `effect_stack_promote(workspace_path=ws, name="p")`.
3. Assert `status == "error"`.
4. Assert error message equals or contains the documented string: `"Vault root not configured -- set vault_root in forge-project.json or personal_vault in ~/.claude/forge.json"` (allow exact spec dash variant).
5. Assert no file written to any vault location.

## Expected Results
- Documented _err returned; no writes.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_promote_vault_unconfigured -v`

## Pass / Fail Criteria
- **Pass:** Exact error message returned.
- **Fail:** Otherwise.
