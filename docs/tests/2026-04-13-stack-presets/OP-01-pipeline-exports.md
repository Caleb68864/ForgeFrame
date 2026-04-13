---
scenario_id: "OP-01"
title: "Pipeline exports serialize/validate/apply/promote/render_vault_body"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - structural
---

# Scenario OP-01: stack_presets Sub-Spec 2 exports

## Description
Verifies `[STRUCTURAL]` -- module exposes `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`, `render_vault_body` (in addition to Sub-Spec 1 names).

## Preconditions
- Module importable post Sub-Spec 2.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines import stack_presets`.
2. Assert each name resolves and is callable: `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`, `render_vault_body`.

## Expected Results
- Five callables present.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_module_exports -v`

## Pass / Fail Criteria
- **Pass:** All present.
- **Fail:** Any missing.
