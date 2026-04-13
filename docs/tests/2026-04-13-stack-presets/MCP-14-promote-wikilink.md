---
scenario_id: "MCP-14"
title: "effect_stack_promote embeds [[My Vid]] wikilink from manifest vault_note_path"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - obsidian
---

# Scenario MCP-14: Promote pulls vault_note_path from workspace manifest

## Description
Verifies `[BEHAVIORAL]` -- when the workspace manifest has `vault_note_path = "Videos/My Vid.md"`, `effect_stack_promote` embeds `[[My Vid]]` in the rendered vault markdown.

## Preconditions
- Workspace with manifest setting `vault_note_path = "Videos/My Vid.md"`.
- A workspace preset saved.

## Steps
1. Call `effect_stack_promote(workspace_path=ws, name="p")`.
2. Read the resulting vault file at `data.vault_path`.
3. Assert body contains `[[My Vid]]` (basename only, no extension, no folder).

## Expected Results
- Wikilink derived from manifest.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_promote_wikilink_from_manifest -v`

## Pass / Fail Criteria
- **Pass:** `[[My Vid]]` present.
- **Fail:** Otherwise.
