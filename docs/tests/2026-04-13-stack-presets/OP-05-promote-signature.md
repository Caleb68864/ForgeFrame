---
scenario_id: "OP-05"
title: "promote_to_vault signature returns Path"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - structural
---

# Scenario OP-05: promote_to_vault signature

## Description
Verifies `[STRUCTURAL]` -- `promote_to_vault(name, workspace_root, vault_root, source_video_note_path=None) -> Path`.

## Preconditions
- A workspace preset already saved.

## Steps
1. Inspect signature; assert parameter names and default `source_video_note_path=None`.
2. Call with valid args; assert return is a `pathlib.Path` pointing under `<vault>/patterns/effect-stacks/`.

## Expected Results
- Signature and return type match.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_promote_signature -v`

## Pass / Fail Criteria
- **Pass:** As documented.
- **Fail:** Otherwise.
