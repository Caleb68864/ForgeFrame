---
scenario_id: "MD-11"
title: "QCReport and TimeRange construction, None optionals, and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-11: QCReport and TimeRange construction, None optionals, and serialization

## Description
Verify `TimeRange` and `QCReport` (from `core/models/qc.py`) -- both plain
`BaseModel` subclasses (not `SerializableMixin`) -- construct correctly,
that required fields are enforced, that optional float fields (`loudness_lufs`,
`true_peak_dbtp`) default to `None`, and that all models round-trip through
Pydantic v2's native `model_dump()` / `model_validate()`.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.qc`

## Test Cases
- **TestTimeRangeRequired**: constructing without `start_seconds` or `end_seconds` raises `ValidationError`
- **TestTimeRangeConstruction**: `TimeRange(start_seconds=1.5, end_seconds=4.0)` constructs correctly
- **TestTimeRangeModelDumpRoundTrip**: `TimeRange.model_validate(tr.model_dump())` produces equal instance
- **TestTimeRangeNegativeValues**: negative `start_seconds` accepted (no non-negative validator)
- **TestTimeRangeZeroDuration**: `start_seconds=end_seconds=0.0` accepted
- **TestQCReportRequired**: constructing `QCReport` without `file_path` raises `ValidationError`
- **TestQCReportDefaults**: `black_frames=[]`, `silence_regions=[]`, `audio_clipping=False`, `loudness_lufs=None`, `true_peak_dbtp=None`, `file_size_bytes=0`, `duration_seconds=0.0`, `checks_passed=[]`, `checks_failed=[]`, `checks_skipped=[]`, `overall_pass=True`
- **TestQCReportLoudnessNone**: `loudness_lufs=None` appears in `model_dump()` as `None`
- **TestQCReportLoudnessSet**: `loudness_lufs=-23.0` stored and round-trips correctly
- **TestQCReportTruePeakNone**: `true_peak_dbtp=None` by default
- **TestQCReportTruePeakSet**: `true_peak_dbtp=-1.0` stored correctly
- **TestQCReportAudioClipping**: `audio_clipping=True` stored correctly
- **TestQCReportOverallFail**: `overall_pass=False` stored correctly
- **TestQCReportBlackFrames**: list of `TimeRange` objects stored in `black_frames`; nested `model_dump()` returns list of dicts
- **TestQCReportSilenceRegions**: same as black frames but for `silence_regions`
- **TestQCReportChecksLists**: `checks_passed`, `checks_failed`, `checks_skipped` lists of strings survive round-trip
- **TestQCReportModelDumpRoundTrip**: `QCReport.model_validate(report.model_dump())` produces equal instance
- **TestQCReportNoSerializableMixin**: confirm `QCReport` does NOT have `to_json` or `to_yaml` methods

## Steps
1. Read source module: `workshop_video_brain/core/models/qc.py`
2. Create `tests/unit/test_qc_model.py`
3. Implement all test cases using Pydantic v2 methods (no `to_json`/`to_yaml`)
4. Run: `uv run pytest tests/unit/test_qc_model.py -v`

## Expected Results
- `file_path` is required for `QCReport`; both fields required for `TimeRange`
- Optional `float | None` fields appear as `None` in `model_dump()` by default
- Nested `TimeRange` objects in `black_frames` / `silence_regions` serialize to dicts
- `model_validate(model_dump())` round-trip produces equal instances
- No `to_json` / `to_yaml` methods (plain `BaseModel`)

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
