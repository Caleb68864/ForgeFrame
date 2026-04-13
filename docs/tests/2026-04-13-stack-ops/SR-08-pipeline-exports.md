---
scenario_id: "SR-08"
title: "Pipeline module exports serialize/deserialize/apply_paste/reorder_stack"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - structural
---

# Scenario SR-08: Pipeline exports

## Description
Verifies `[STRUCTURAL]` -- `pipelines/stack_ops.py` exports the four documented callables with correct signatures.

## Preconditions
- Sub-Spec 2 implementation merged.
- `workshop_video_brain.edit_mcp.pipelines.stack_ops` importable.

## Steps
1. Import `stack_ops` module.
2. Assert callables exist: `serialize_stack`, `deserialize_stack`, `apply_paste`, `reorder_stack`.
3. Verify signatures via `inspect.signature`:
   - `serialize_stack(project, clip_ref) -> dict`
   - `deserialize_stack(stack_dict) -> list[str]`
   - `apply_paste(project, target_clip_ref, stack_dict, mode) -> None`
   - `reorder_stack(project, clip_ref, from_index, to_index) -> None`

## Expected Results
- All exports present, signatures match.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_exports -v`

## Pass / Fail Criteria
- **Pass:** Exports present with correct signatures.
- **Fail:** Missing export or signature mismatch.
