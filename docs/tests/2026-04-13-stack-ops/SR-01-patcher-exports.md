---
scenario_id: "SR-01"
title: "Patcher exports stack-mutation methods"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - structural
---

# Scenario SR-01: Patcher exports stack-mutation methods

## Description
Verifies the `[STRUCTURAL]` criterion that `patcher.py` exports the three new functions with the documented signatures.

## Preconditions
- Sub-Spec 1 implementation merged.
- `workshop_video_brain.edit_mcp.adapters.kdenlive.patcher` importable.

## Steps
1. Import `patcher` module.
2. Assert `hasattr(patcher, "insert_effect_xml")`.
3. Assert `hasattr(patcher, "remove_effect")`.
4. Assert `hasattr(patcher, "reorder_effects")`.
5. Inspect signatures via `inspect.signature` and verify parameter names and order:
   - `insert_effect_xml(project, clip_ref, xml_string: str, position: int) -> None`
   - `remove_effect(project, clip_ref, effect_index: int) -> None`
   - `reorder_effects(project, clip_ref, from_index: int, to_index: int) -> None`

## Expected Results
- All three callables exported.
- Signatures match documented contract exactly.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_exports -v`

## Pass / Fail Criteria
- **Pass:** All asserts succeed.
- **Fail:** ImportError, missing attribute, or signature mismatch.
