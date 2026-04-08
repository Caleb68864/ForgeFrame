---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: "4b"
title: "Kdenlive Adapter + Timelines + Subtitles"
dependencies: ["4a"]
date: 2026-04-08
---

# Sub-Spec 4b: Kdenlive Adapter + Timelines + Subtitles

## Scope

Kdenlive internal project model, XML parser with opaque passthrough for unknown elements, versioned project writer, project validator with severity-leveled reports, timeline intent model, review timeline generator (ranked markers → Kdenlive project with guide markers), selects timeline generator, chapter marker generator, subtitle pipeline (transcript → SRT).

## Interface Contracts

### Provides (to Sub-Spec 5)

- **Kdenlive project model** in `core/models/kdenlive.py`:
  - `KdenliveProject(version, profile, media_refs, tracks, clips, markers, guides, subtitles, transitions, opaque_elements)`
  - `Track(id, type, clips: list[ClipRef])`
  - `ClipRef(producer_id, track_id, in_point, out_point, position)`
  - `Guide(position, label, category, comment)`
  - `OpaqueElement(tag, xml_string)` -- preserved unknown XML

- **Parser/serializer** in `edit_mcp/adapters/kdenlive/`:
  - `parse_project(path: Path) -> KdenliveProject`
  - `serialize_project(project: KdenliveProject, output_path: Path) -> None`
  - `patch_project(project: KdenliveProject, intents: list[TimelineIntent]) -> KdenliveProject`

- **Validator** in `edit_mcp/adapters/kdenlive/validator.py`:
  - `validate_project(project: KdenliveProject, workspace: Workspace) -> ValidationReport`

- **Timeline intent model** in `core/models/timeline.py`:
  - `TimelineIntent` union type: `AddClip`, `TrimClip`, `InsertGap`, `AddMarker`, `AddGuide`, `AddSubtitleRegion`, `AddTransition`, `CreateTrack`

- **Pipeline outputs** in `edit_mcp/pipelines/`:
  - `build_review_timeline(markers, assets, workspace, mode="ranked") -> Path` -- returns path to generated .kdenlive
  - `build_selects_timeline(selects, assets, workspace) -> Path`
  - `generate_chapter_markers(markers) -> list[Guide]`
  - `generate_srt(transcript, max_line_length, max_duration) -> str`

### Requires (from Sub-Spec 4a)

- Ranked markers, selects list
- Transcript and silence data in workspace

## Implementation Steps

### Step 1: Create Kdenlive project model

**Create** `core/models/kdenlive.py`:
- `KdenliveProject` Pydantic model with fields for: document version, project profile (fps, width, height), media references (producer elements), tracks, clip references with in/out/position, guides/markers, transition stubs, and `opaque_elements: list[OpaqueElement]` for everything the parser doesn't understand
- Keep this model editorial -- no raw XML types in fields that business logic touches

### Step 2: Create Kdenlive XML parser

**Create** `edit_mcp/adapters/kdenlive/parser.py`:
- Uses `xml.etree.ElementTree` for parsing
- Parses known elements: `<mlt>`, `<profile>`, `<producer>`, `<playlist>`, `<tractor>`, `<track>`, `<entry>`, `<transition>`, `<filter>`, `<property>`, Kdenlive-specific `<kdenlive_producer>`, `<markers>`
- For each known element: extract into model fields
- For unknown elements: store as `OpaqueElement(tag=tag, xml_string=ET.tostring(elem))` -- preserved for round-trip
- Captures document version from `<mlt>` root attributes
- Returns `KdenliveProject` model
- Logs warnings for unsupported constructs, does not crash

### Step 3: Create Kdenlive serializer

**Create** `edit_mcp/adapters/kdenlive/serializer.py`:
- Builds XML from `KdenliveProject` model
- Re-inserts all `OpaqueElement` entries at their original positions (or end if position unknown)
- Writes to output path with snapshot creation first
- Versioned naming: `{title}_v{N}.kdenlive` in `projects/working_copies/`
- Validates output XML is well-formed before declaring success

### Step 4: Create Kdenlive patcher

**Create** `edit_mcp/adapters/kdenlive/patcher.py`:
- `patch_project(project, intents)` -- applies a list of `TimelineIntent` operations to the project model
- `AddGuide` intent: adds a guide/marker at specified position with label
- `AddClip` intent: adds a clip reference to specified track
- Returns modified `KdenliveProject` (immutable -- returns new instance)

### Step 5: Create project validator

**Create** `edit_mcp/adapters/kdenlive/validator.py`:
- `validate_project(project, workspace)` returns `ValidationReport`
- Checks: media paths exist on disk, clip in/out within media duration, track indices valid, no overlapping clips on same track, markers within project duration, required metadata present (profile, at least one track)
- Each issue is a `ValidationItem(severity, category, message, location)`
- Severity: info, warning, error, blocking_error

### Step 6: Create timeline intent model

**Expand** `core/models/timeline.py`:
- Base `TimelineIntent` with `intent_type` discriminator
- Concrete intents: `AddClip(producer_id, track_id, in_point, out_point, position)`, `TrimClip(clip_ref, new_in, new_out)`, `InsertGap(track_id, position, duration)`, `AddGuide(position, label, category, comment)`, `AddSubtitleRegion(start, end, text)`, `AddTransition(type, track, left_clip, right_clip, duration)`, `CreateTrack(type, name)`

### Step 7: Build review timeline generator

**Complete** `edit_mcp/pipelines/review_timeline.py`:
- `build_review_timeline(markers, assets, workspace, mode="ranked")`:
  1. Create new KdenliveProject from workspace profile
  2. Create video + audio track pair
  3. For each marker (in ranked or chronological order): add clip ref covering marker's time range
  4. Add Kdenlive guide for each marker with label: `"{category}: {reason} (confidence: {score})"` 
  5. Serialize to `projects/working_copies/{title}_review_v{N}.kdenlive`
  6. Generate companion markdown report: `reports/review_report_{timestamp}.md`
  7. Return path to generated project

### Step 8: Build selects timeline generator

**Complete** `edit_mcp/pipelines/selects_timeline.py`:
- `build_selects_timeline(selects, assets, workspace)`:
  1. Create new KdenliveProject
  2. Add only the selected segments as clip refs
  3. Add guides for each select
  4. Serialize to working copies
  5. Return path

### Step 9: Create chapter marker generator

**Add to** review_timeline or new file:
- `generate_chapter_markers(markers)` -- filter for `chapter_candidate` markers, create `Guide` objects with chapter labels
- `export_chapters_to_note(chapters) -> str` -- markdown formatted chapter list with timestamps

### Step 10: Create subtitle pipeline

**Create** `edit_mcp/pipelines/subtitle_pipeline.py`:
- `generate_srt(transcript, max_line_length=42, max_duration=5.0) -> str` -- formats transcript segments as SRT
- `save_srt(srt_content, workspace, filename) -> Path` -- saves to workspace
- `import_srt(srt_path) -> list[SubtitleCue]` -- parses SRT into model
- `export_srt(cues: list[SubtitleCue]) -> str` -- model back to SRT string

### Step 11: Write tests

**Create**:
- `tests/unit/test_kdenlive_parser.py` -- parse sample .kdenlive, verify model fields, verify opaque passthrough
- `tests/unit/test_kdenlive_writer.py` -- serialize model to XML, verify well-formed, verify versioned naming
- `tests/unit/test_validator.py` -- test each validation check (missing media, invalid clips, etc.)
- `tests/integration/test_kdenlive_roundtrip.py` -- parse sample → serialize → parse again, verify equivalence

**Create** `tests/fixtures/projects/sample_tutorial.kdenlive` -- a minimal valid Kdenlive project file with 2 tracks, 3 clips, 1 guide. Can be created by hand or exported from Kdenlive.

## Verification Commands

```bash
uv run pytest tests/unit/test_kdenlive_parser.py tests/unit/test_kdenlive_writer.py tests/unit/test_validator.py -v
uv run pytest tests/integration/test_kdenlive_roundtrip.py -v
```

## Acceptance Criteria

- [ ] Kdenlive internal model covers required elements
- [ ] Parser reads .kdenlive XML into internal model
- [ ] Unknown XML elements preserved as opaque nodes
- [ ] Parser captures document version
- [ ] Parser fails gracefully on unsupported constructs
- [ ] Writer outputs versioned .kdenlive files to working_copies/
- [ ] Writer creates snapshot before writing
- [ ] Written project opens in Kdenlive without errors (manual QA)
- [ ] Validator checks media paths, clip ranges, track integrity, markers, metadata
- [ ] Validator returns structured report with severity levels
- [ ] Timeline intent model supports all required operations
- [ ] Review timeline generator creates Kdenlive project with guide markers
- [ ] External markdown review report generated
- [ ] Selects timeline generator creates filtered project
- [ ] Chapter markers exported to guides + note
- [ ] SRT generation with configurable line length and duration
- [ ] SRT imports cleanly into Kdenlive (manual QA)
