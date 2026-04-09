---
scenario_id: "MD-12"
title: "ClipCandidate, ClipExport, SocialPost construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-12: ClipCandidate, ClipExport, SocialPost construction and serialization

## Description
Verify all models in `core/models/social.py` -- `ClipCandidate`, `ClipExport`,
`SocialPost` -- construct correctly, that required positional fields on
`ClipCandidate` are enforced, that score fields default to `0.0`, and that all
models round-trip through JSON and YAML.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.social`

## Test Cases
- **TestClipCandidateRequired**: constructing without `start_seconds`, `end_seconds`, or `duration_seconds` raises `ValidationError`
- **TestClipCandidateDefaults**: `hook_text=""`, `content_summary=""`, `hook_strength=0.0`, `clarity=0.0`, `engagement=0.0`, `overall_score=0.0`, `source_step=""`
- **TestClipCandidateAllFields**: all fields set; `model_dump()` returns matching dict
- **TestClipCandidateScoreBoundary**: score fields at `0.0` and `1.0` accepted; `1.5` also accepted (no range validator)
- **TestClipCandidateJsonRoundTrip**: `ClipCandidate.from_json(cc.to_json())` produces equal instance
- **TestClipCandidateYamlRoundTrip**: `ClipCandidate.from_yaml(cc.to_yaml())` produces equal instance
- **TestClipExportDefaultConstruction**: `ClipExport()` constructs without error
- **TestClipExportDefaults**: `clip_id=""`, `start_seconds=0.0`, `end_seconds=0.0`, `title=""`, `caption=""`, `description=""`, `hashtags=[]`, `aspect_ratio="9:16"`, `source_video=""`
- **TestClipExportAspectRatioDefault**: `aspect_ratio` defaults to `"9:16"`
- **TestClipExportAspectRatioOverride**: `aspect_ratio="16:9"` stored correctly
- **TestClipExportHashtags**: non-empty list of hashtag strings survives `model_dump()` / `model_validate()`
- **TestClipExportMutableDefaultIsolation**: two `ClipExport()` instances do not share the same `hashtags` list
- **TestClipExportJsonRoundTrip**: `ClipExport.from_json(ce.to_json())` produces equal instance
- **TestSocialPostDefaultConstruction**: `SocialPost()` constructs without error
- **TestSocialPostDefaults**: `platform="youtube"`, `post_text=""`, `hashtags=[]`, `clip_title=""`
- **TestSocialPostPlatforms**: `"instagram"`, `"tiktok"`, `"twitter"` all accepted (no enum; any string valid)
- **TestSocialPostHashtags**: non-empty hashtags list survives JSON round-trip
- **TestSocialPostYamlRoundTrip**: `SocialPost.from_yaml(sp.to_yaml())` produces equal instance

## Steps
1. Read source module: `workshop_video_brain/core/models/social.py`
2. Create `tests/unit/test_social_model.py`
3. Implement all test cases
4. Run: `uv run pytest tests/unit/test_social_model.py -v`

## Expected Results
- `start_seconds`, `end_seconds`, `duration_seconds` are required for `ClipCandidate`
- Score fields accept `0.0`, `1.0`, and values beyond `1.0` (no range validators)
- `aspect_ratio` defaults to `"9:16"` in `ClipExport`
- `platform` defaults to `"youtube"` in `SocialPost`
- Mutable list defaults are isolated between instances
- Full JSON and YAML round-trips succeed

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
