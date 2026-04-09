---
scenario_id: "MD-06"
title: "ClipLabel construction, defaults, and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-06: ClipLabel construction, defaults, and serialization

## Description
Verify `ClipLabel` (from `core/models/clips.py`) -- the sole model in that
module -- constructs with all defaults when no arguments are supplied, accepts
all fields, and round-trips through JSON and YAML. Edge cases focus on the two
mutable list defaults (`topics`, `tags`), the speech density boundary values,
and empty-string fields.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.clips`

## Test Cases
- **TestClipLabelDefaultConstruction**: `ClipLabel()` constructs without error
- **TestClipLabelDefaults**: `clip_ref=""`, `content_type="unlabeled"`, `shot_type="medium"`, `has_speech=False`, `speech_density=0.0`, `summary=""`, `duration=0.0`, `source_path=""`
- **TestClipLabelDefaultTopicsEmpty**: `topics` defaults to `[]`
- **TestClipLabelDefaultTagsEmpty**: `tags` defaults to `[]`
- **TestClipLabelMutableDefaultIsolation**: two `ClipLabel()` instances do not share the same `topics` list object
- **TestClipLabelAllFields**: pass every field; `model_dump()` returns matching dict
- **TestClipLabelContentTypes**: accepted values include `"tutorial_step"`, `"materials_overview"`, `"talking_head"`, `"b_roll"`, `"unlabeled"` (no enum; any string is valid -- confirm no error)
- **TestClipLabelSpeechDensityBoundary**: `speech_density=0.0` and `speech_density=1.0` both accepted
- **TestClipLabelSpeechDensityBeyondRange**: `speech_density=1.5` accepted (no range validator in source -- confirm no error)
- **TestClipLabelHasSpeechTrue**: `has_speech=True` stored correctly
- **TestClipLabelTopicsPopulated**: list of noun phrase strings survives `model_dump()` / `model_validate()`
- **TestClipLabelJsonRoundTrip**: `ClipLabel.from_json(label.to_json())` produces equal instance
- **TestClipLabelYamlRoundTrip**: `ClipLabel.from_yaml(label.to_yaml())` produces equal instance
- **TestClipLabelEmptyStringFields**: all string fields accept `""` without error

## Steps
1. Read source module: `workshop_video_brain/core/models/clips.py`
2. Create `tests/unit/test_clips_model.py`
3. Implement all test cases, including mutable default isolation check
4. Run: `uv run pytest tests/unit/test_clips_model.py -v`

## Expected Results
- `ClipLabel()` constructs with all documented defaults
- Mutable list fields (`topics`, `tags`) are independent between instances
- No range validation on `speech_density` -- boundary and over-boundary values are accepted
- Full field round-trip through JSON and YAML without data loss

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
