---
scenario_id: "MD-09"
title: "MaterialList, ReviewNote, ScriptDraft, Shot, ShotPlan construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-09: MaterialList, ReviewNote, ScriptDraft, Shot, ShotPlan construction and serialization

## Description
Verify all models in `core/models/planning.py` -- `Shot`, `ShotPlan`,
`ScriptDraft`, `ReviewNote`, `MaterialList` -- construct correctly, that
`ShotType` enum values are flattened to strings via `use_enum_values=True`,
and that all models round-trip through JSON and YAML.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.planning`

## Test Cases
- **TestShotRequired**: constructing `Shot` without `type` raises `ValidationError`
- **TestShotEnumStoredAsString**: `shot.type` is a `str` (e.g., `"a_roll"`), not a `ShotType` instance
- **TestShotDefaults**: `description=""`, `beat_ref=""`, `priority=0`
- **TestShotAllFields**: all four fields round-trip through `model_dump()` / `model_validate()`
- **TestShotInvalidType**: passing an unknown shot type string raises `ValidationError`
- **TestShotPlanDefaultConstruction**: `ShotPlan()` constructs without error; `shots=[]`
- **TestShotPlanWithShots**: list of `Shot` objects survives JSON round-trip
- **TestScriptDraftDefaultConstruction**: `ScriptDraft()` constructs without error
- **TestScriptDraftDefaults**: `sections={}`, `tone=""`, `target_length=0`
- **TestScriptDraftSections**: `sections={"intro": "Welcome..."}` survives `model_dump()` / `model_validate()`
- **TestScriptDraftTargetLength**: `target_length=300` stored correctly
- **TestReviewNoteDefaultConstruction**: `ReviewNote()` constructs without error
- **TestReviewNoteDefaults**: all five list fields default to `[]`
- **TestReviewNoteAllLists**: populate all five lists; `model_dump()` returns correct structure
- **TestReviewNoteMutableDefaultIsolation**: two `ReviewNote()` instances do not share list objects
- **TestMaterialListDefaultConstruction**: `MaterialList()` constructs without error
- **TestMaterialListDefaults**: `materials=[]`, `tools=[]`
- **TestMaterialListPopulated**: non-empty `materials` and `tools` lists survive JSON round-trip
- **TestScriptDraftJsonRoundTrip**: `ScriptDraft.from_json(sd.to_json())` produces equal instance
- **TestReviewNoteYamlRoundTrip**: `ReviewNote.from_yaml(rn.to_yaml())` produces equal instance

## Steps
1. Read source module: `workshop_video_brain/core/models/planning.py`
2. Create `tests/unit/test_planning_model.py`
3. Implement all test cases
4. Run: `uv run pytest tests/unit/test_planning_model.py -v`

## Expected Results
- `Shot.type` is required; invalid string raises `ValidationError`
- `use_enum_values=True` means `shot.type == "a_roll"` rather than `ShotType.a_roll`
- All list fields default to `[]` and are isolated between instances
- Full field round-trip through JSON and YAML without data loss

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
