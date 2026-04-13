---
scenario_id: "IO-13"
title: "Vault markdown body renders header/description/tags/effect-table + wikilink"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
  - obsidian
---

# Scenario IO-13: Vault markdown rendering

## Description
Verifies `[BEHAVIORAL]` -- the vault file body contains: name header, description text, tags line, effect summary table, and a "Referenced from" wikilink line ONLY when a `source_video_note_path` was provided (omitted otherwise).

## Preconditions
- `tmp_path` vault root.
- Two `Preset` instances differing only in whether the save path includes a source note context.

## Steps
1. Save preset A via `save_preset(scope="vault")` while invoking helper that includes a source video note path of `Videos/My Video.md`. Read file.
   - Assert body contains a header line with the preset name (e.g., `# my-preset`).
   - Assert body contains the description text.
   - Assert body contains a tags line (e.g., `Tags: ` followed by tags or a list).
   - Assert body contains a markdown table whose header row references effects (e.g., columns include `mlt_service`).
   - Assert body contains `[[My Video]]` wikilink (NOT the full path -- just the basename without extension).
   - Assert body contains the literal phrase "Referenced from" preceding the wikilink.
2. Save preset B without a source note. Read file.
   - Assert body still contains header/description/tags/table.
   - Assert body does NOT contain "Referenced from" or any `[[...]]` wikilink.

## Expected Results
- Body structure complete in both cases; wikilink + "Referenced from" only present in case A.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_vault_markdown_body -v`

## Pass / Fail Criteria
- **Pass:** Both case structures match.
- **Fail:** Missing component or wikilink leaks into B.
