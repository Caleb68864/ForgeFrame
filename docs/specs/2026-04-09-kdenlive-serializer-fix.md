---
title: "Fix Kdenlive Serializer -- Proper Bin Registration and UUID Generation"
project: ForgeFrame
repo: Caleb68864/ForgeFrame
date: 2026-04-09
author: Caleb Bennett
quality_scores:
  outcome: 5
  scope: 5
  edges: 4
  criteria: 4
  decomposition: 5
  total: 23
---

# Fix Kdenlive Serializer -- Proper Bin Registration and UUID Generation

## Outcome

Generated .kdenlive files open in Kdenlive without "Project corrupted. Clip X not found in project bin" errors. All clips (media and titles) are properly registered in the project bin with UUIDs, clip types, and required Kdenlive metadata.

## Context

The Kdenlive serializer at `edit_mcp/adapters/kdenlive/serializer.py` generates XML that is structurally valid MLT but missing Kdenlive-specific metadata. When opened, Kdenlive reports "Project corrupted" for clips used in the timeline but not properly registered in the bin.

**Root cause:** Kdenlive requires:
1. Every clip used in the timeline must have a `main_bin` playlist entry
2. Every producer must have a `kdenlive:uuid` property (auto-generated UUID)
3. Every producer must have a `kdenlive:id` property (sequential integer, unique)
4. Every producer must have a `kdenlive:clip_type` property (0=video, 1=audio, 2=title)
5. The `main_bin` playlist must be set as `producer="main_bin"` on the root `<mlt>` element
6. Timeline playlists need paired A/B playlists per track (Kdenlive uses pairs)
7. The tractor needs `mix` transitions for audio and `frei0r.cairoblend` for video compositing

**Current serializer missing:**
- No `main_bin` playlist generation
- No `kdenlive:uuid` on producers
- No `kdenlive:id` on producers
- No `kdenlive:clip_type` on producers
- No `kdenlive:folderid` on producers (needed for bin organization)
- No black_track producer (background)
- No paired playlists (Kdenlive expects playlist pairs per track)
- No internal transitions (mix for audio, cairoblend for video)
- No `LC_NUMERIC="C"` on root element
- Frame rate written as integer instead of proper num/den

**Reference:** See `references/mlt-xml-reference.md` for MLT XML structure. The user-provided corrupted file in this spec shows the correct structure that Kdenlive expects.

## Requirements

1. Generated .kdenlive files must open in Kdenlive without "corrupted" warnings
2. All producers must have `kdenlive:uuid`, `kdenlive:id`, `kdenlive:clip_type` properties
3. A `main_bin` playlist must contain entries for all producers used in the project
4. The serializer must generate paired playlists per track (Kdenlive convention)
5. A `black_track` producer must be generated as the background
6. Internal transitions (mix, cairoblend) must be generated for audio/video tracks
7. Root `<mlt>` element must have `LC_NUMERIC="C"` and `producer="main_bin"`
8. Existing tests must continue to pass
9. The parser must still be able to read the new format (round-trip)
10. Backward compatibility: files written by the old serializer must still be parseable

## Sub-Specs

### Sub-Spec 1: Producer Metadata Generation

**Scope:** Add UUID generation, kdenlive:id sequencing, clip type detection, and folder ID assignment to all producers during serialization.

**Files:**
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/kdenlive.py` (add uuid/clip_type fields if needed)
- Test: `tests/unit/test_serializer_bin.py`

**Acceptance criteria:**
- [ ] Every serialized producer has a `kdenlive:uuid` property (valid UUID4 in `{...}` format)
- [ ] Every serialized producer has a `kdenlive:id` property (sequential integer starting at 2)
- [ ] Every serialized producer has a `kdenlive:clip_type` property (0 for video/avformat, 1 for audio, 2 for kdenlivetitle)
- [ ] Every serialized producer has a `kdenlive:folderid` property (default `-1` for root bin)
- [ ] UUIDs are stable: serializing the same project twice produces the same UUIDs (deterministic from producer id)
- [ ] Existing producer properties preserved (resource, mlt_service, etc.)
- [ ] Tests: round-trip (serialize → parse → serialize produces same output)

**Dependencies:** none

### Sub-Spec 2: Main Bin Playlist Generation

**Scope:** Generate a `main_bin` playlist containing entries for all producers, set as the root producer on `<mlt>`.

**Files:**
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Test: `tests/unit/test_serializer_bin.py`

**Acceptance criteria:**
- [ ] Root `<mlt>` element has `producer="main_bin"` attribute
- [ ] Root `<mlt>` element has `LC_NUMERIC="C"` attribute
- [ ] A `<playlist id="main_bin">` element exists containing entries for ALL producers
- [ ] `main_bin` has `kdenlive:docproperties.version` property set to `"1.1"`
- [ ] `main_bin` has `kdenlive:docproperties.profile` property matching the project profile
- [ ] `main_bin` has `kdenlive:docproperties.uuid` property (project-level UUID)
- [ ] Tests: generated XML contains main_bin with correct producer count

**Dependencies:** 1

### Sub-Spec 3: Track Structure and Internal Transitions

**Scope:** Generate proper paired playlists, black_track, and internal transitions (mix for audio, cairoblend for video).

**Files:**
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Test: `tests/unit/test_serializer_bin.py`

**Acceptance criteria:**
- [ ] A `black_track` producer is generated with `mlt_service=color`, `resource=black`, `length=2147483647`
- [ ] Each video track gets a paired playlist (content + empty pair)
- [ ] Each audio track gets a paired playlist (content + empty pair)
- [ ] Tractor includes `black_track` as first track
- [ ] Tractor includes `mix` transition for each audio track pair (a_track=0, b_track=N, always_active=1, sum=1)
- [ ] Tractor includes `frei0r.cairoblend` transition for each video track pair (a_track=0, b_track=N, always_active=1)
- [ ] Frame rate written as proper num/den (not truncated integer)
- [ ] Profile element includes `progressive`, `sample_aspect_num/den`, `display_aspect_num/den`
- [ ] Tests: generated XML opens in Kdenlive without corruption warnings (validated by checking XML structure matches expected Kdenlive format)

**Dependencies:** 1, 2

### Sub-Spec 4: Integration Tests

**Scope:** End-to-end tests that create a project, serialize it, and validate the output matches Kdenlive's expected format.

**Files:**
- Create: `tests/integration/test_kdenlive_bin_roundtrip.py`

**Acceptance criteria:**
- [ ] Test: create project with 3 video clips + 2 title clips → serialize → all producers in main_bin
- [ ] Test: serialize → parse → serialize produces structurally equivalent XML
- [ ] Test: generated XML validated against Kdenlive's expected structure (main_bin, UUIDs, clip types, paired playlists, transitions)
- [ ] Test: projects with existing opaque elements (filters, transitions from Phase 3) survive round-trip
- [ ] All existing serializer/parser tests still pass

**Dependencies:** 1, 2, 3

## Edge Cases

1. **Empty project:** No producers → main_bin is empty, still valid
2. **Title-only clips:** kdenlivetitle producers need clip_type=2 and special handling
3. **Mixed audio/video:** Audio-only producers need clip_type=1
4. **Existing opaque elements:** Filters and transitions from Phase 3 (AddEffect, AddComposition) must survive the new serialization
5. **Backward compatibility:** Old .kdenlive files without main_bin must still parse correctly

## Out of Scope

- Kdenlive effect/filter parameter validation
- Rendering from generated files (that's the render pipeline's job)
- Proxy clip registration in the bin
- Multiple sequences/timelines (single timeline only)

## Verification

1. `uv run pytest tests/ -v` -- all existing tests pass
2. Create a test project with video + title clips → serialize → open in Kdenlive → no corruption warnings
3. Round-trip: parse existing .kdenlive → serialize → parse → compare models
