---
scenario_id: "PAT-01"
title: "Patcher exports get/set/list_effects with correct signatures"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - structural
---

# Scenario PAT-01: Patcher exports get/set/list_effects with correct signatures

## Description
Verifies [STRUCTURAL] criteria in Sub-Spec 1 -- that `patcher.py` exports three new methods (`get_effect_property`, `set_effect_property`, `list_effects`) with the exact signatures documented in the spec. Guards against additive-only preference being violated via refactor drift.

## Preconditions
- Sub-Spec 1 implementation complete.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` is importable.

## Steps
1. Import the patcher module in a pytest unit test.
2. Use `inspect.signature` to assert `get_effect_property(clip_ref, effect_index, property_name) -> str | None`.
3. Use `inspect.signature` to assert `set_effect_property(clip_ref, effect_index, property_name, value: str) -> None`.
4. Use `inspect.signature` to assert `list_effects(clip_ref) -> list[dict]`.
5. Confirm no pre-existing patcher method has been modified (diff vs. previous commit or compare to reference list of methods captured in the test).

## Expected Results
- All three methods exist on the patcher class/module.
- Parameter names and type hints match the spec.
- Return annotations are present and correct.
- No pre-existing methods have been renamed or had their signatures altered.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_effect_properties.py::test_exports_and_signatures -v`

## Pass / Fail Criteria
- **Pass:** All signature assertions succeed; additive-only property holds.
- **Fail:** Any method missing, wrong signature, or existing method mutated.
