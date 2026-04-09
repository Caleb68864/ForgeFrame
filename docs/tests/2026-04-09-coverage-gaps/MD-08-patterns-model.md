---
scenario_id: "MD-08"
title: "BuildData, BuildStep, MaterialItem, Measurement, BuildTip construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-08: BuildData, BuildStep, MaterialItem, Measurement, BuildTip construction and serialization

## Description
Verify all models in `core/models/patterns.py` -- `MaterialItem`, `Measurement`,
`BuildStep`, `BuildTip`, `BuildData` -- construct correctly, that required
fields are enforced, that `timestamp` defaults to `0.0` across all leaf models,
and that the aggregate `BuildData` model round-trips through JSON and YAML with
nested lists intact.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.patterns`

## Test Cases
- **TestMaterialItemRequired**: constructing without `name` raises `ValidationError`
- **TestMaterialItemDefaults**: `quantity=""`, `notes=""`, `timestamp=0.0`
- **TestMaterialItemAllFields**: all four fields round-trip through `model_dump()` / `model_validate()`
- **TestMeasurementRequired**: constructing without `value`, `unit`, or `context` raises `ValidationError` for each missing field
- **TestMeasurementDefaults**: `timestamp=0.0`
- **TestMeasurementAllFields**: all four fields survive JSON round-trip
- **TestBuildStepRequired**: constructing without `number` or `description` raises `ValidationError`
- **TestBuildStepDefaults**: `timestamp=0.0`
- **TestBuildStepAllFields**: `number=3`, `description="Sand edges"`, `timestamp=42.5` round-trips correctly
- **TestBuildStepNumberZero**: `number=0` accepted (no lower-bound validator)
- **TestBuildTipRequired**: constructing without `text` or `tip_type` raises `ValidationError`
- **TestBuildTipDefaults**: `timestamp=0.0`
- **TestBuildTipTypes**: `tip_type="tip"` and `tip_type="warning"` both accepted (no enum; any string valid)
- **TestBuildDataDefaultConstruction**: `BuildData()` constructs without error
- **TestBuildDataDefaults**: `project_title=""`, `materials=[]`, `measurements=[]`, `steps=[]`, `tips=[]`
- **TestBuildDataMutableDefaultIsolation**: two `BuildData()` instances do not share the same list objects
- **TestBuildDataAllFields**: populate all nested lists; `model_dump()` returns correct nested structure
- **TestBuildDataJsonRoundTrip**: `BuildData.from_json(bd.to_json())` produces equal instance
- **TestBuildDataYamlRoundTrip**: `BuildData.from_yaml(bd.to_yaml())` produces equal instance
- **TestBuildDataTimestampFloat**: fractional timestamps (e.g., `12.345`) survive serialization

## Steps
1. Read source module: `workshop_video_brain/core/models/patterns.py`
2. Create `tests/unit/test_patterns_model.py`
3. Implement all test cases
4. Run: `uv run pytest tests/unit/test_patterns_model.py -v`

## Expected Results
- All required fields (`name`, `value`, `unit`, `context`, `number`, `description`, `text`, `tip_type`) raise `ValidationError` when absent
- `timestamp=0.0` is the default across all leaf models
- Nested list structures in `BuildData` survive JSON and YAML round-trips
- Mutable default lists in `BuildData` are isolated between instances

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
