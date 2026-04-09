---
scenario_id: "MD-15"
title: "ValidationItem and ValidationReport construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-15: ValidationItem and ValidationReport construction and serialization

## Description
Verify `ValidationItem` and `ValidationReport` (from `core/models/validation.py`)
construct correctly, that `ValidationSeverity` enum values are stored as strings
via `use_enum_values=True`, that the required `severity` field is enforced, and
that both models round-trip through JSON and YAML.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.validation`

## Test Cases
- **TestValidationItemRequired**: constructing `ValidationItem` without `severity` raises `ValidationError`
- **TestValidationItemEnumStoredAsString**: `item.severity` is a `str` (e.g., `"info"`), not a `ValidationSeverity` instance
- **TestValidationItemDefaults**: `category=""`, `message=""`, `location=""`
- **TestValidationItemAllSeverities**: `"info"`, `"warning"`, `"error"`, `"blocking_error"` all accepted
- **TestValidationItemInvalidSeverity**: unknown severity string raises `ValidationError`
- **TestValidationItemAllFields**: all four fields set; `model_dump()` returns matching dict
- **TestValidationItemJsonRoundTrip**: `ValidationItem.from_json(vi.to_json())` produces equal instance
- **TestValidationItemYamlRoundTrip**: `ValidationItem.from_yaml(vi.to_yaml())` produces equal instance
- **TestValidationReportDefaultConstruction**: `ValidationReport()` constructs without error
- **TestValidationReportDefaults**: `items=[]`, `summary=""`
- **TestValidationReportWithItems**: list of `ValidationItem` objects survives JSON round-trip
- **TestValidationReportSummary**: non-empty `summary` string stored and round-trips correctly
- **TestValidationReportMutableDefaultIsolation**: two `ValidationReport()` instances do not share the same `items` list
- **TestValidationReportMixedSeverities**: report with `info`, `warning`, `error`, `blocking_error` items; all severities preserved through `from_json(to_json())`
- **TestValidationReportJsonRoundTrip**: `ValidationReport.from_json(vr.to_json())` produces equal instance
- **TestValidationReportYamlRoundTrip**: `ValidationReport.from_yaml(vr.to_yaml())` produces equal instance

## Steps
1. Read source module: `workshop_video_brain/core/models/validation.py`
2. Create `tests/unit/test_validation_model.py`
3. Implement all test cases
4. Run: `uv run pytest tests/unit/test_validation_model.py -v`

## Expected Results
- `severity` is required for `ValidationItem`; invalid string raises `ValidationError`
- `item.severity` is a plain string, not a `ValidationSeverity` instance
- All four severity levels accepted: `"info"`, `"warning"`, `"error"`, `"blocking_error"`
- `items` list is isolated between `ValidationReport` instances
- Full JSON and YAML round-trips preserve nested `ValidationItem` objects

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
