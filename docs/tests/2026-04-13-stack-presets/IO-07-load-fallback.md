---
scenario_id: "IO-07"
title: "load_preset workspace-first, falls back to vault"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-07: load_preset two-tier fallback

## Description
Verifies `[BEHAVIORAL]` -- `load_preset(name, workspace_root, vault_root)` prefers the workspace copy; if absent, returns the vault copy. Returned value is a validated `Preset`.

## Preconditions
- `tmp_path` workspace and vault roots.

## Steps
1. **Workspace-first case:** Save `Preset(name="dup")` to workspace AND a different `Preset(name="dup", description="vault-version")` to vault. Call `load_preset("dup", ws, vault)` and assert returned preset's description is the workspace one (not "vault-version").
2. **Fallback case:** Remove from workspace; call `load_preset("dup", ws, vault)`; assert returned preset's description is "vault-version".
3. Assert both returns are `Preset` instances (not dicts).

## Expected Results
- Workspace wins when present; vault loaded when workspace absent.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_load_fallback -v`

## Pass / Fail Criteria
- **Pass:** Both cases resolve as documented.
- **Fail:** Wrong tier returned.
