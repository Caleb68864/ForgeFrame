---
scenario_id: "MD-03"
title: "KdenliveProject and sub-models construction and serialization"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-03: KdenliveProject and sub-models construction and serialization

## Description
Verify all models in `core/models/kdenlive.py` -- `ProjectProfile`, `Producer`,
`PlaylistEntry`, `Playlist`, `Track`, `Guide`, `OpaqueElement`, and
`KdenliveProject` -- construct correctly with defaults, accept all fields, and
round-trip through JSON and YAML without data loss. Edge cases target optional
string fields (`None` vs empty string), the `tractor: dict | None` field, and
empty list defaults.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models.kdenlive`

## Test Cases
- **TestProjectProfileDefaults**: `width=1920`, `height=1080`, `fps=25.0`, `colorspace=None`
- **TestProjectProfileAllFields**: pass all four fields; `model_dump()` returns matching dict
- **TestProducerRequired**: constructing `Producer` without `id` raises `ValidationError`
- **TestProducerDefaults**: `resource=""`, `properties={}` when only `id` is supplied
- **TestProducerProperties**: arbitrary key-value pairs survive `model_dump()` / `model_validate()`
- **TestPlaylistEntryGap**: default `producer_id=""` represents a gap as documented
- **TestPlaylistEntryAllFields**: `producer_id`, `in_point`, `out_point` all round-trip correctly
- **TestPlaylistDefaults**: `entries` is an empty list by default
- **TestPlaylistWithEntries**: list of `PlaylistEntry` objects preserved through JSON round-trip
- **TestTrackDefaults**: `track_type="video"`, `name=None`
- **TestTrackAudio**: `track_type="audio"` stored verbatim (no enum validation)
- **TestGuideRequired**: constructing `Guide` without `position` raises `ValidationError`
- **TestGuideOptionalNone**: `category=None`, `comment=None` by default
- **TestOpaqueElementRequired**: constructing without `tag` or `xml_string` raises `ValidationError`
- **TestOpaqueElementPositionHintNone**: `position_hint=None` by default
- **TestKdenliveProjectDefaults**: `version="7"`, `title=""`, all lists empty, `tractor=None`
- **TestKdenliveProjectFull**: construct with producers, tracks, playlists, guides, opaque_elements, tractor dict; JSON round-trip preserves all
- **TestKdenliveProjectTractorDict**: `tractor` accepts arbitrary dict and survives round-trip
- **TestKdenliveProjectYamlRoundTrip**: full project round-trips through `to_yaml()` / `from_yaml()`

## Steps
1. Read source module: `workshop_video_brain/core/models/kdenlive.py`
2. Create `tests/unit/test_kdenlive_model.py`
3. Implement all test cases
4. Run: `uv run pytest tests/unit/test_kdenlive_model.py -v`

## Expected Results
- All defaults match documented source values
- Required fields (`id`, `position`, `tag`, `xml_string`) raise `ValidationError` when absent
- Optional `None` fields are preserved as `None` in `model_dump()` and JSON output
- `tractor={"foo": "bar"}` survives JSON serialization unchanged
- YAML round-trip produces equal model instances

## Pass / Fail Criteria
- Pass: All construction, validation, and serialization tests pass
- Fail: Any test fails
