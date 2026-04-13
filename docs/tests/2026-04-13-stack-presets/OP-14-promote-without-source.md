---
scenario_id: "OP-14"
title: "promote_to_vault with source=None omits 'Referenced from' line"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-14: promote_to_vault without source

## Description
Verifies `[BEHAVIORAL]` -- when `source_video_note_path is None`, the rendered body has no "Referenced from" line and no wikilinks.

## Preconditions
- A preset saved in workspace.

## Steps
1. `dst = promote_to_vault("p", ws, vault, source_video_note_path=None)`.
2. Read `dst`; assert it does NOT contain `"Referenced from"`.
3. Assert it does NOT contain `[[` (no wikilinks).
4. Assert other body sections (header/description/effects table) are still present.

## Expected Results
- Body complete minus the wikilink line.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_promote_without_source -v`

## Pass / Fail Criteria
- **Pass:** No wikilink/referenced-from; rest intact.
- **Fail:** Otherwise.
