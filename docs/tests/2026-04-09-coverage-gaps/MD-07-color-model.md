---
scenario_id: "MD-07"
title: "ColorAnalysis construction, None optionals, and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-07: ColorAnalysis construction, None optionals, and serialization

## Description
Verify `ColorAnalysis` (from `core/models/color.py`) -- a plain `BaseModel`
(not `SerializableMixin`) -- constructs correctly with only the required
`file_path` field, that all optional fields default to `None` or their
documented defaults, and that the model serializes and validates correctly
using Pydantic v2's native `model_dump()` and `model_validate()`.
Since this model does not inherit `SerializableMixin`, it lacks `to_json` /
`to_yaml`; tests must use `model_dump()` and `model_validate()` directly.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.color`

## Test Cases
- **TestColorAnalysisRequired**: constructing without `file_path` raises `ValidationError`
- **TestColorAnalysisDefaults**: `color_space=None`, `color_primaries=None`, `color_transfer=None`, `bit_depth=None`, `is_hdr=False`, `recommendations=[]`
- **TestColorAnalysisAllFields**: pass all fields; `model_dump()` returns matching dict
- **TestColorAnalysisIsHdrTrue**: `is_hdr=True` stored correctly
- **TestColorAnalysisBitDepthValues**: `bit_depth=8`, `bit_depth=10`, `bit_depth=12` all accepted
- **TestColorAnalysisBitDepthNone**: `bit_depth=None` explicitly set and survives `model_dump()`
- **TestColorAnalysisRecommendations**: non-empty list of strings survives `model_dump()` / `model_validate()`
- **TestColorAnalysisDefaultRecommendationsMutableIsolation**: two instances do not share the same `recommendations` list (note: this is a plain `[]` default; confirm isolation with Pydantic v2)
- **TestColorAnalysisNoSerializableMixin**: confirm `ColorAnalysis` does NOT have `to_json` or `to_yaml` methods
- **TestColorAnalysisModelDumpRoundTrip**: `ColorAnalysis.model_validate(ca.model_dump())` produces equal instance
- **TestColorAnalysisModelDumpJsonRoundTrip**: `ColorAnalysis.model_validate_json(ca.model_dump_json())` produces equal instance
- **TestColorAnalysisNoneFieldsInDump**: `model_dump()` includes `color_space: None` rather than omitting the key

## Steps
1. Read source module: `workshop_video_brain/core/models/color.py`
2. Create `tests/unit/test_color_model.py`
3. Implement all test cases (no `to_json`/`to_yaml` -- use Pydantic v2 methods directly)
4. Run: `uv run pytest tests/unit/test_color_model.py -v`

## Expected Results
- `file_path` is the only required field
- All optional fields default to `None` or their documented scalar defaults
- `model_dump()` includes `None` values for optional fields
- Full round-trip via `model_validate(model_dump())` produces equal instance
- `to_json` / `to_yaml` are absent (plain `BaseModel`, not `SerializableMixin`)

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
