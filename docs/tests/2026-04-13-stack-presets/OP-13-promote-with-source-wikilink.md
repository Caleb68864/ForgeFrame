---
scenario_id: "OP-13"
title: "promote_to_vault embeds [[My Video]] wikilink when source path provided"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
  - obsidian
---

# Scenario OP-13: promote_to_vault wikilink embedding

## Description
Verifies `[BEHAVIORAL]` -- `promote_to_vault(name, ws, vault, source_video_note_path=Path("Videos/My Video.md"))` writes vault markdown containing `[[My Video]]` (basename without extension).

## Preconditions
- A preset already saved in workspace `<ws>/stacks/p.yaml`.

## Steps
1. Call `dst = promote_to_vault("p", ws, vault, source_video_note_path=Path("Videos/My Video.md"))`.
2. Assert `dst.exists()`.
3. Read `dst` body; assert it contains the literal substring `[[My Video]]` (no extension, no folder).
4. Assert it also contains the phrase "Referenced from" preceding the wikilink.

## Expected Results
- Wikilink rendered with basename only.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_promote_with_source -v`

## Pass / Fail Criteria
- **Pass:** Wikilink present.
- **Fail:** Otherwise.
