---
scenario_id: "MD-13"
title: "All TimelineIntent subclass construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-13: All TimelineIntent subclass construction and serialization

## Description
Verify every `TimelineIntent` subclass in `core/models/timeline.py` --
`TransitionIntent`, `SubtitleCue`, `AddClip`, `TrimClip`, `InsertGap`,
`AddGuide`, `AddSubtitleRegion`, `AddTransition`, `CreateTrack`, `RemoveClip`,
`MoveClip`, `SplitClip`, `RippleDelete`, `SetClipSpeed`, `AudioFade`,
`SetTrackMute`, `SetTrackVisibility`, `AddEffect`, `AddComposition` --
construct with all defaults, accept their documented fields, and round-trip
through JSON and YAML.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.timeline`

## Test Cases
- **TestTimelineIntentBaseConstruction**: `TimelineIntent()` constructs without error
- **TestTransitionIntentDefaults**: `type=""`, `track_ref=""`, `left_clip_ref=""`, `right_clip_ref=""`, `duration_frames=0`, `reason=""`
- **TestSubtitleCueDefaults**: `start_seconds=0.0`, `end_seconds=0.0`, `text=""`
- **TestAddClipDefaults**: `producer_id=""`, `track_id=""`, `track_ref=""`, `in_point=0`, `out_point=0`, `position=-1`, `source_path=""`
- **TestAddClipPositionMinusOne**: `position=-1` (append sentinel) is the default
- **TestTrimClipDefaults**: `clip_ref=""`, `new_in=0`, `new_out=0`
- **TestInsertGapDefaults**: `track_id=""`, `position=0`, `duration_frames=0`
- **TestAddGuideDefaults**: `position_frames=0`, `label=""`, `category=None`, `comment=None`
- **TestAddGuideOptionalNone**: `category=None` and `comment=None` survive `model_dump()`
- **TestAddSubtitleRegionDefaults**: `start_seconds=0.0`, `end_seconds=0.0`, `text=""`
- **TestAddTransitionDefaults**: `type=""`, `track_ref=""`, `left_clip_ref=""`, `right_clip_ref=""`, `duration_frames=0`
- **TestCreateTrackDefaults**: `track_type="video"`, `name=""`
- **TestCreateTrackAudio**: `track_type="audio"` stored correctly
- **TestRemoveClipDefaults**: `track_ref=""`, `clip_index=0`
- **TestMoveClipDefaults**: `track_ref=""`, `from_index=0`, `to_index=0`
- **TestSplitClipDefaults**: `track_ref=""`, `clip_index=0`, `split_at_frame=0`
- **TestRippleDeleteDefaults**: `track_ref=""`, `clip_index=0`
- **TestSetClipSpeedDefaults**: `track_ref=""`, `clip_index=0`, `speed=1.0`
- **TestSetClipSpeedHalfSpeed**: `speed=0.5` stored correctly
- **TestAudioFadeDefaults**: `track_ref=""`, `clip_index=0`, `fade_type="in"`, `duration_frames=24`
- **TestAudioFadeFadeOut**: `fade_type="out"` stored correctly
- **TestSetTrackMuteDefaults**: `track_ref=""`, `muted=True`
- **TestSetTrackMuteUnmute**: `muted=False` stored correctly
- **TestSetTrackVisibilityDefaults**: `track_ref=""`, `visible=True`
- **TestSetTrackVisibilityHidden**: `visible=False` stored correctly
- **TestAddEffectDefaults**: `track_index=0`, `clip_index=0`, `effect_name=""`, `params={}`
- **TestAddEffectWithParams**: `params={"brightness": "0.5"}` survives JSON round-trip
- **TestAddCompositionDefaults**: `track_a=0`, `track_b=0`, `start_frame=0`, `end_frame=0`, `composition_type=""`, `params={}`
- **TestAddCompositionWithParams**: `params={"alpha": "1"}` survives JSON round-trip
- **TestJsonRoundTripSample**: `AddClip`, `AudioFade`, `AddEffect`, `AddComposition` each round-trip through `from_json(x.to_json())`
- **TestYamlRoundTripSample**: same four models round-trip through `from_yaml(x.to_yaml())`

## Steps
1. Read source module: `workshop_video_brain/core/models/timeline.py`
2. Create `tests/unit/test_timeline_model.py`
3. Implement all test cases (one test class per intent subclass is recommended)
4. Run: `uv run pytest tests/unit/test_timeline_model.py -v`

## Expected Results
- All 18 subclasses construct with zero arguments (all fields have defaults)
- `position=-1` sentinel is preserved in `AddClip`
- `duration_frames=24` is the `AudioFade` default
- `muted=True` and `visible=True` are the respective defaults for mute/visibility intents
- `params` dict fields survive JSON and YAML round-trips
- Optional `None` fields (`AddGuide.category`, `AddGuide.comment`) appear as `None` in `model_dump()`

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
