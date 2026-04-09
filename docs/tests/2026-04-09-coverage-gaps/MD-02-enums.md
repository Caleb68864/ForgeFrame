---
scenario_id: "MD-02"
title: "Enum values accessible and comparable as strings"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-02: Enum values accessible and comparable as strings

## Description
Verify every enum defined in `core/models/enums.py` -- `ProjectStatus`,
`MarkerCategory`, `JobStatus`, `ShotType`, `ProxyStatus`, `TranscriptStatus`,
`AnalysisStatus`, `ValidationSeverity` -- exposes the correct string values,
supports equality comparison with plain strings (all are `str, Enum`), and
contains the exact set of members documented in the source.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.enums`

## Test Cases
- **TestProjectStatusValues**: all 10 members present (`idea`, `outlining`, `scripting`, `filming`, `ingesting`, `editing`, `review`, `rendering`, `published`, `archived`)
- **TestMarkerCategoryValues**: all 14 members present
- **TestJobStatusValues**: all 5 members present (`queued`, `running`, `succeeded`, `failed`, `cancelled`)
- **TestShotTypeValues**: all 7 members present (`a_roll`, `overhead`, `closeup`, `measurement`, `insert`, `glamour`, `pickup`)
- **TestProxyStatusValues**: all 5 members present (`not_needed`, `pending`, `generating`, `ready`, `failed`)
- **TestTranscriptStatusValues**: all 4 members present (`pending`, `processing`, `completed`, `failed`)
- **TestAnalysisStatusValues**: all 4 members present (same as TranscriptStatus)
- **TestValidationSeverityValues**: all 4 members present (`info`, `warning`, `error`, `blocking_error`)
- **TestStrComparison**: `ProjectStatus.idea == "idea"` is `True` for every enum
- **TestStrInheritance**: `isinstance(ProjectStatus.published, str)` is `True`
- **TestInvalidMember**: accessing a non-existent member raises `ValueError` (via `ProjectStatus("bogus")`)
- **TestJsonSerializable**: `json.dumps(ProjectStatus.idea)` does not raise

## Steps
1. Read source module: `workshop_video_brain/core/models/enums.py`
2. Create `tests/unit/test_enums_model.py`
3. Implement parameterized tests (use `pytest.mark.parametrize`) covering each enum's member list
4. Run: `uv run pytest tests/unit/test_enums_model.py -v`

## Expected Results
- Every enum member's `.value` matches the documented string literal
- String equality comparisons with raw strings return `True`
- `isinstance(member, str)` is `True` for all members
- `json.dumps(member)` produces the quoted string value, not a repr
- Invalid member lookup raises `ValueError`

## Pass / Fail Criteria
- Pass: All member presence, string-comparison, and serialization tests pass
- Fail: Any test fails
