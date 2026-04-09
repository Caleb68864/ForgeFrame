---
title: "Phase 3 -- Pipeline Completeness"
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

# Phase 3 -- Pipeline Completeness

## Outcome

Nine features that close every gap between the video-editing-guide handbook pipeline and ForgeFrame's actual capabilities. After implementation: capture prep checklists from shot plans, VFR detection with CFR transcode, full renders with platform presets (YouTube/Vimeo/master), automated post-render QC, color analysis and LUT application to Kdenlive projects, generic effect insertion on clips, Kdenlive project profile configuration, PiP/wipe compositing, and workspace archiving. Each feature has MCP tools and optional skills, following the existing model -> pipeline -> tool -> skill pattern.

## Context

ForgeFrame Phase 1+2 is complete: 16 skills, 73 MCP tools, 21 pipelines, 1,242 tests. A video-editing-guide handbook was written covering the full production pipeline (preproduction through archiving). Gap analysis revealed 9 missing capabilities. The design document at `docs/plans/2026-04-09-phase3-pipeline-completeness-design.md` specifies a hybrid approach: build 3 shared infrastructure pieces first, then 9 vertical feature slices.

Existing codebase patterns:
- **MCP tools**: `@mcp.tool()` decorator, return `_ok(data)` / `_err(message)`, use `_validate_workspace_path()` and `_require_workspace()`
- **Pipelines**: Pure functions returning dataclass reports, per-item try-catch, log warnings, add to report.errors
- **Models**: Pydantic in `core/models/`, re-exported via `__init__.py` `__all__`
- **Kdenlive patcher**: Deep-copies project, applies `TimelineIntent` list, supports 15 intent types including `AddClip`, `TrimClip`, `AddTransition`, `SetClipSpeed`, `AudioFade`
- **FFprobe**: `probe_media(path) -> MediaAsset` with fps, duration, codec, resolution, file_hash
- **Render profiles**: YAML files in `templates/render/`, loaded via `load_profile(name) -> RenderProfile`
- **Skills**: `ff-` prefix, SKILL.md in `workshop-video-brain/skills/ff-*/`

## Requirements

1. All new MCP tools MUST return `{"status": "success"/"error", "data"/"message": ...}` via `_ok()`/`_err()`
2. All new pipeline functions MUST be pure (no side effects except file writes to workspace)
3. All new models MUST be Pydantic, added to `core/models/__init__.py` `__all__`
4. All new skills MUST use `ff-` prefix
5. All features MUST handle missing/empty inputs gracefully (return empty results, not exceptions)
6. All features MUST be idempotent on re-run
7. All existing 1,242 tests MUST still pass
8. New `TimelineIntent` types MUST deep-copy project (never mutate input)
9. Infrastructure sub-specs (1-3) MUST complete before dependent feature sub-specs

## Sub-Specs

### Sub-Spec 1: FFprobe Extended (Infrastructure)

**Scope:** Extend `probe_media()` to detect VFR, extract color metadata, and measure loudness from media files.

**Files:**
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/probe.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/media.py` (add fields to MediaAsset)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export if new models)
- Test: `tests/unit/test_probe_extended.py`

**Acceptance criteria:**
- [ ] `MediaAsset` gains `is_vfr: bool` field (default False)
- [ ] `MediaAsset` gains `color_space: str | None` field (e.g., "bt709", "bt2020")
- [ ] `MediaAsset` gains `color_primaries: str | None` field
- [ ] `MediaAsset` gains `color_transfer: str | None` field
- [ ] VFR detection: compare `r_frame_rate` and `avg_frame_rate` from ffprobe JSON; if divergence > 5%, set `is_vfr = True`
- [ ] VFR detection: also check `codec_tag_string` and container-level VFR flags when available
- [ ] Color metadata extracted from video stream's `color_space`, `color_primaries`, `color_transfer` fields in ffprobe JSON
- [ ] `LoudnessResult` dataclass added: `input_i: float` (integrated LUFS), `input_tp: float` (true peak dBTP), `input_lra: float` (loudness range LU)
- [ ] `measure_loudness(path: Path) -> LoudnessResult | None` function added: runs `ffmpeg -i {path} -af loudnorm=print_format=json -f null -` and parses JSON output; returns None on failure
- [ ] All new fields default to None/False when ffprobe data is missing (no exceptions)
- [ ] Existing `probe_media()` tests still pass unchanged
- [ ] New tests: VFR file detection, CFR file non-detection, color metadata extraction, loudness measurement, missing metadata graceful handling

**Dependencies:** none

### Sub-Spec 2: Kdenlive Filter Insertion Engine (Infrastructure)

**Scope:** Add `AddEffect` and `AddComposition` intent types to the Kdenlive patcher, enabling programmatic insertion of `<filter>` and `<transition>` elements into .kdenlive projects.

**Files:**
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/timeline.py` (add AddEffect, AddComposition intents)
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` (handle new intents)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- Test: `tests/unit/test_filter_insertion.py`

**Acceptance criteria:**
- [ ] `AddEffect` intent: fields `track_index: int`, `clip_index: int`, `effect_name: str`, `params: dict[str, str]`
- [ ] `AddComposition` intent: fields `track_a: int`, `track_b: int`, `start_frame: int`, `end_frame: int`, `composition_type: str`, `params: dict[str, str]`
- [ ] Patcher handles `AddEffect`: creates `<filter>` OpaqueElement with `mlt_service={effect_name}`, `track`, `clip_index` attributes and `<property>` children from params dict; appended to `project.opaque_elements` with `position_hint="after_tractor"` (matching existing SetClipSpeed/AudioFade pattern)
- [ ] Patcher handles `AddComposition`: creates `<transition>` OpaqueElement with `mlt_service={composition_type}`, `a_track`/`b_track`, `in`/`out` frame range, and `<property>` children from params; appended to `project.opaque_elements` with `position_hint="after_tractor"`
- [ ] Both intents deep-copy the project before mutation
- [ ] Effect insertion preserves existing filters on the same clip (appends, does not replace)
- [ ] Composition insertion preserves existing transitions
- [ ] Invalid track/clip indices return clear error in patch report (not exception)
- [ ] Round-trip test: parse -> add effect -> serialize -> parse again -> effect still present
- [ ] Round-trip test: parse -> add composition -> serialize -> parse again -> composition present
- [ ] Existing patcher tests still pass

**Dependencies:** none

### Sub-Spec 3: Render Profile Expansion (Infrastructure)

**Scope:** Add 5 new render profile YAML files and extend the render executor to support Fast Start (movflags +faststart) and codec availability checking.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/templates/render/youtube-1080p.yaml`
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/templates/render/youtube-4k.yaml`
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/templates/render/vimeo-hq.yaml`
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/templates/render/master-prores.yaml`
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/templates/render/master-dnxhr.yaml`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/profiles.py` (fast-start flag)
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/executor.py` (codec check + fast-start)
- Test: `tests/unit/test_render_profiles_extended.py`

**Acceptance criteria:**
- [ ] `youtube-1080p.yaml`: H.264 High Profile, 1920x1080, AAC-LC 48kHz, ~8 Mbps video, movflags +faststart, BT.709
- [ ] `youtube-4k.yaml`: H.264 High Profile, 3840x2160, AAC-LC 48kHz, ~35 Mbps video, movflags +faststart, BT.709
- [ ] `vimeo-hq.yaml`: ProRes 422 HQ in MOV container, AAC-LC 48kHz 320kbps
- [ ] `master-prores.yaml`: ProRes 422 HQ in MOV, PCM audio 48kHz
- [ ] `master-dnxhr.yaml`: DNxHR HQX in MOV, PCM audio 48kHz
- [ ] `RenderProfile` model gains `fast_start: bool` field (default False)
- [ ] `RenderProfile` model gains `movflags: str | None` field
- [ ] Executor appends `-movflags +faststart` to FFmpeg args when `fast_start=True`
- [ ] `check_codec_available(codec_name: str) -> bool` function: runs `ffmpeg -codecs` and checks for encoder availability
- [ ] Executor calls `check_codec_available()` before render; returns clear error if encoder missing
- [ ] `list_profiles()` returns all 5 new profiles plus existing ones
- [ ] Each new YAML loads and validates as RenderProfile without errors
- [ ] Tests: load each profile, codec check (mock subprocess), fast-start flag in FFmpeg args

**Dependencies:** none

### Sub-Spec 4: Capture Prep Skill

**Scope:** New skill `ff-capture-prep` that reads the shot plan from a workspace and generates a pre-shoot checklist covering camera settings, audio setup, lighting notes, and sync strategy.

**Files:**
- Create: `workshop-video-brain/skills/ff-capture-prep/SKILL.md`
- Create: `workshop-video-brain/src/workshop_video_brain/production_brain/skills/capture_prep.py`
- Test: `tests/unit/test_capture_prep.py`

**Acceptance criteria:**
- [ ] `generate_capture_checklist(shot_plan: ShotPlan, target_resolution: str, target_fps: int) -> str` function returns markdown checklist
- [ ] Checklist sections: Camera Settings (resolution, fps, color profile), Audio Setup (mic type, gain, monitoring), Lighting Notes (per shot type), Sync Strategy (clap/slate/timecode), Shot Order (optimized for setup changes)
- [ ] Reads shot plan from workspace `reports/shot_plan.json` if it exists
- [ ] Falls back to generating generic checklist if no shot plan found
- [ ] SKILL.md instructs Claude to read workspace, call `generate_capture_checklist()`, and present the checklist with personalized notes
- [ ] Skill registered in plugin.json
- [ ] Tests: with full shot plan, with empty shot plan, with various resolution/fps combos

**Dependencies:** none

### Sub-Spec 5: VFR Detection and CFR Transcode

**Scope:** MCP tool to detect VFR media and a separate tool to transcode VFR files to constant frame rate.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/vfr_check.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add 2 tools)
- Test: `tests/unit/test_vfr_check.py`

**Acceptance criteria:**
- [ ] `check_vfr(workspace_root: Path) -> VFRReport` scans all video files in workspace, returns list of VFR files with details
- [ ] `VFRReport` dataclass: `files_checked: int`, `vfr_files: list[VFRFile]`, `all_cfr: bool`
- [ ] `VFRFile` dataclass: `path: str`, `r_frame_rate: str`, `avg_frame_rate: str`, `divergence_pct: float`
- [ ] `transcode_to_cfr(source: Path, target_fps: int | None = None) -> Path` transcodes VFR file to CFR using `ffmpeg -i {src} -vsync cfr -r {fps} {out}`
- [ ] If `target_fps` is None, uses the `avg_frame_rate` from probe as target
- [ ] Output file placed alongside source with `_cfr` suffix (e.g., `clip_cfr.mp4`)
- [ ] MCP tool `media_check_vfr(workspace_path: str) -> dict` wraps `check_vfr()`
- [ ] MCP tool `media_transcode_cfr(workspace_path: str, file_path: str, target_fps: int = 0) -> dict` wraps `transcode_to_cfr()`
- [ ] Tests: VFR detection (mock ffprobe output), CFR passthrough, transcode command construction

**Dependencies:** Sub-Spec 1 (FFprobe Extended -- uses `is_vfr` field)

### Sub-Spec 6: Full Render Tool

**Scope:** MCP tool for full-quality renders using named presets, with codec availability checking and progress reporting.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/render_final.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add tool)
- Test: `tests/unit/test_render_final.py`

**Acceptance criteria:**
- [ ] `render_final(workspace_root: Path, profile_name: str, project_file: str | None = None, output_name: str | None = None) -> RenderResult` function (if project_file is None, uses most recently modified .kdenlive in projects/working_copies/)
- [ ] `RenderResult` dataclass: `output_path: str`, `profile_used: str`, `duration_seconds: float`, `file_size_bytes: int`, `codec_info: str`
- [ ] Checks codec availability before render; returns error if encoder missing
- [ ] Creates snapshot before render (using existing snapshot system)
- [ ] Output placed in `workspace/renders/{output_name or profile_name}_{timestamp}.{ext}`
- [ ] Supports all profiles from Sub-Spec 3 plus existing profiles
- [ ] MCP tool `render_final(workspace_path: str, profile: str, project_file: str = "", output_name: str = "") -> dict`
- [ ] MCP tool `render_list_profiles() -> dict` returns all available profile names with descriptions
- [ ] Tests: render with each profile (mock FFmpeg), missing codec error, output path construction

**Dependencies:** Sub-Spec 3 (Render Profile Expansion)

### Sub-Spec 7: QC Automation Tool

**Scope:** Automated post-render quality checks: black frame detection, audio clipping scan, loudness measurement, file size sanity.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/qc_check.py`
- Create: `workshop-video-brain/src/workshop_video_brain/core/models/qc.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add tool)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- Test: `tests/unit/test_qc_check.py`

**Acceptance criteria:**
- [ ] `QCReport` model: `file_path: str`, `black_frames: list[TimeRange]`, `silence_regions: list[TimeRange]`, `audio_clipping: bool`, `loudness_lufs: float | None`, `true_peak_dbtp: float | None`, `file_size_bytes: int`, `duration_seconds: float`, `checks_passed: list[str]`, `checks_failed: list[str]`, `checks_skipped: list[str]`, `overall_pass: bool`
- [ ] `TimeRange` model: `start_seconds: float`, `end_seconds: float`
- [ ] `run_qc(file_path: Path, checks: list[str] | None = None) -> QCReport`
- [ ] Check: `black_frames` -- uses `ffmpeg -vf blackdetect=d=0.5:pix_th=0.10` and parses output
- [ ] Check: `silence` -- uses `ffmpeg -af silencedetect=n=-50dB:d=1.0` and parses output
- [ ] Check: `loudness` -- uses `measure_loudness()` from Sub-Spec 1
- [ ] Check: `clipping` -- uses `ffmpeg -af astats=metadata=1` and checks for samples at 0 dBFS
- [ ] Check: `file_size` -- sanity check: warns if < 1KB or > 10GB for a typical render
- [ ] If a check's FFmpeg filter is unavailable, adds to `checks_skipped` (not failure)
- [ ] `overall_pass` is True only if `checks_failed` is empty
- [ ] MCP tool `qc_check(file_path: str, checks: str = "") -> dict` (checks is comma-separated list or empty for all)
- [ ] Tests: black frames detected, silence detected, loudness measured, clipping detected, missing filter skipped, clean file passes all

**Dependencies:** Sub-Spec 1 (FFprobe Extended -- uses `measure_loudness()`)

### Sub-Spec 8: Color Analysis and LUT Application

**Scope:** MCP tools to analyze color metadata of media files and apply LUT files to clips in Kdenlive projects.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/color_tools.py`
- Create: `workshop-video-brain/src/workshop_video_brain/core/models/color.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add 2 tools)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- Test: `tests/unit/test_color_tools.py`

**Acceptance criteria:**
- [ ] `ColorAnalysis` model: `file_path: str`, `color_space: str | None`, `color_primaries: str | None`, `color_transfer: str | None`, `bit_depth: int | None`, `is_hdr: bool`, `recommendations: list[str]`
- [ ] `analyze_color(file_path: Path) -> ColorAnalysis` reads color metadata from ffprobe (via extended probe) and adds recommendations (e.g., "Source is BT.709 SDR -- no conversion needed for YouTube" or "Source is BT.2020 -- consider BT.709 conversion for SDR delivery")
- [ ] `apply_lut_to_project(project: KdenliveProject, track_index: int, clip_index: int, lut_path: str, effect_name: str = "avfilter.lut3d") -> KdenliveProject` uses `AddEffect` intent with configurable effect_name (default "avfilter.lut3d", may need "frei0r.lut3d" on some builds) and `params={"av.file": lut_path}`
- [ ] MCP tool `color_analyze(file_path: str) -> dict` wraps `analyze_color()`
- [ ] MCP tool `color_apply_lut(workspace_path: str, project_file: str, track: int, clip: int, lut_path: str) -> dict` loads project, applies LUT, saves
- [ ] Snapshot created before modifying project file
- [ ] Tests: color analysis with BT.709 source, BT.2020 source, missing metadata, LUT application round-trip, invalid track/clip index error

**Dependencies:** Sub-Spec 1 (FFprobe Extended), Sub-Spec 2 (Kdenlive Filter Engine)

### Sub-Spec 9: Generic Effect Application Tool

**Scope:** MCP tool to add any named Kdenlive/MLT effect to a clip with arbitrary parameters.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add tool)
- Test: `tests/unit/test_effect_apply.py`

**Acceptance criteria:**
- [ ] `apply_effect(project: KdenliveProject, track_index: int, clip_index: int, effect_name: str, params: dict[str, str]) -> KdenliveProject` uses `AddEffect` intent from Sub-Spec 2
- [ ] `list_common_effects() -> list[dict]` returns a curated list of common effect names with descriptions (transform, position_and_zoom, lift_gamma_gain, curves, chroma_key, gaussian_blur, etc.) -- informational only, not a validation gate
- [ ] MCP tool `effect_add(workspace_path: str, project_file: str, track: int, clip: int, effect_name: str, params: str) -> dict` (params is JSON string of key-value pairs)
- [ ] MCP tool `effect_list_common() -> dict` returns the curated list
- [ ] Does NOT validate effect_name against a hardcoded list (Kdenlive effect availability varies by build)
- [ ] Snapshot created before modifying project
- [ ] Multiple effects can be added to the same clip (append, not replace)
- [ ] Tests: add single effect, add multiple effects to same clip, invalid track/clip index, empty params

**Dependencies:** Sub-Spec 2 (Kdenlive Filter Engine)

### Sub-Spec 10: Project Profile Setup

**Scope:** MCP tool to configure Kdenlive project resolution, frame rate, and color space in the .kdenlive XML.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/project_profile.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add tool)
- Test: `tests/unit/test_project_profile.py`

**Acceptance criteria:**
- [ ] `set_project_profile(project: KdenliveProject, width: int, height: int, fps_num: int, fps_den: int, colorspace: int | None = None) -> KdenliveProject` modifies the `<profile>` element attributes
- [ ] Common colorspace values documented: 601 (SD/BT.601), 709 (HD/BT.709), 240 (SMPTE 240M)
- [ ] `match_profile_to_source(source_path: Path) -> dict` reads source media via probe and returns recommended project settings (width, height, fps_num, fps_den, colorspace)
- [ ] MCP tool `project_setup_profile(workspace_path: str, project_file: str, width: int, height: int, fps_num: int, fps_den: int, colorspace: int = 709) -> dict`
- [ ] MCP tool `project_match_source(workspace_path: str, source_file: str) -> dict` returns recommended settings from source media
- [ ] Snapshot created before modifying project
- [ ] Tests: set profile on parsed project, match profile to 1080p30 source, match profile to 4K24 source, round-trip (set -> serialize -> parse -> verify)

**Dependencies:** Sub-Spec 1 (FFprobe Extended -- uses probe data for match_profile_to_source)

### Sub-Spec 11: Compositing Tools

**Scope:** MCP tools for picture-in-picture layouts and wipe/dissolve compositions between tracks in Kdenlive projects.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py`
- Create: `workshop-video-brain/src/workshop_video_brain/core/models/compositing.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add 2 tools)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- Test: `tests/unit/test_compositing.py`

**Acceptance criteria:**
- [ ] `PipLayout` model: `x: int`, `y: int`, `width: int`, `height: int` (position of overlay within frame)
- [ ] `PipPreset` enum: `top_left`, `top_right`, `bottom_left`, `bottom_right`, `center`, `custom`
- [ ] `get_pip_layout(preset: PipPreset, frame_width: int, frame_height: int, pip_scale: float = 0.25) -> PipLayout` calculates position from preset
- [ ] `apply_pip(project: KdenliveProject, overlay_track: int, base_track: int, start_frame: int, end_frame: int, layout: PipLayout) -> KdenliveProject` uses `AddComposition` intent with `composition_type="composite"` and geometry property in Kdenlive format `"{x}/{y}:{w}x{h}:{opacity}"` (e.g., `"1440/810:480x270:100"`)
- [ ] `apply_wipe(project: KdenliveProject, track_a: int, track_b: int, start_frame: int, end_frame: int, wipe_type: str = "dissolve") -> KdenliveProject` uses `AddComposition` with `composition_type="luma"` or `"composite"` depending on wipe type
- [ ] MCP tool `composite_pip(workspace_path: str, project_file: str, overlay_track: int, base_track: int, start_frame: int, end_frame: int, preset: str = "bottom_right", scale: float = 0.25) -> dict`
- [ ] MCP tool `composite_wipe(workspace_path: str, project_file: str, track_a: int, track_b: int, start_frame: int, end_frame: int, wipe_type: str = "dissolve") -> dict`
- [ ] Snapshot created before modifying project
- [ ] Tests: PiP each preset, custom PiP position, wipe dissolve, wipe luma, invalid tracks error, round-trip

**Dependencies:** Sub-Spec 2 (Kdenlive Filter Engine -- uses AddComposition)

### Sub-Spec 12: Project Archive Tool

**Scope:** MCP tool to bundle a workspace with its renders and project files into a dated archive for long-term storage.

**Files:**
- Create: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/archive.py`
- Create: `workshop-video-brain/src/workshop_video_brain/core/models/archive.py`
- Modify: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add tool)
- Modify: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- Test: `tests/unit/test_archive.py`

**Acceptance criteria:**
- [ ] `ArchiveManifest` model: `workspace_title: str`, `archive_path: Path`, `created_at: str`, `files_included: int`, `total_size_bytes: int`, `includes_renders: bool`, `includes_raw_media: bool`
- [ ] `create_archive(workspace_root: Path, output_dir: Path, include_renders: bool = True, include_raw: bool = False, format: str = "tar.gz") -> ArchiveManifest`
- [ ] Supported formats: `tar.gz` (default), `zip`
- [ ] Always includes: project files (.kdenlive), workspace.yaml, reports/, transcripts
- [ ] `include_renders=True` adds `renders/` directory
- [ ] `include_raw=False` by default (raw media is large; explicit opt-in)
- [ ] Archive named: `{workspace_title}_{YYYY-MM-DD}.{ext}`
- [ ] Streams to archive (tarfile/zipfile) rather than loading all into memory
- [ ] MCP tool `project_archive(workspace_path: str, output_dir: str, include_renders: bool = True, include_raw: bool = False, format: str = "tar.gz") -> dict`
- [ ] Tests: archive with renders, archive without renders, archive with raw, zip format, manifest accuracy, empty workspace handling

**Dependencies:** none

## Edge Cases

1. **VFR false positives**: Use >5% divergence threshold. Some CFR containers report slightly different r_frame_rate vs avg_frame_rate due to metadata rounding.
2. **Missing FFmpeg filters**: blackdetect/silencedetect/astats may not be in all builds. Skip unavailable checks and report in `checks_skipped` -- never fail the whole QC pipeline.
3. **Kdenlive effect names vary by build**: Do NOT validate effect names against a hardcoded list. Accept any string. Kdenlive handles unknown effects at render time.
4. **ProRes/DNxHR encoder unavailability**: `check_codec_available()` must run before render. Return actionable error: "Encoder 'prores_ks' not found. Install FFmpeg with ProRes support or use a different profile."
5. **Large workspace archives**: Stream to tar/zip (use tarfile.open / zipfile.ZipFile in streaming mode). Do not load entire workspace into memory. Report progress for >1GB archives.
6. **Color metadata missing from source**: Many consumer cameras don't tag color_space. Default assumption: BT.709 for HD, BT.601 for SD. Add recommendation: "No color metadata found -- assuming BT.709."
7. **Existing filters on clips**: AddEffect MUST append to existing filters, never replace. Test with clips that already have effects applied.

## Out of Scope

- Effect parameter discovery/autocompletion (depends on installed libraries per build)
- Visual scope rendering (waveform/vectorscope image generation)
- HDR workflows (BT.2020/PQ/HLG pipeline -- future work)
- Multi-project archive (archive one workspace at a time)
- Render queue/batch system (one render at a time via tool)
- CLI commands for new tools (MCP tools only in Phase 3; CLI can follow later)

## Verification

1. Run full test suite: `uv run pytest tests/ -v` -- all 1,242+ existing tests pass, plus new tests
2. Process a sample video through extended probe: confirm VFR flag, color metadata, loudness values
3. Load each new render profile: `load_profile("youtube-1080p")` etc. -- all validate
4. Parse a .kdenlive project, add an effect via AddEffect, serialize, re-parse: effect present
5. Parse a .kdenlive project, add a PiP composition, serialize, re-parse: composition present
6. Run QC check on a known-good render: all checks pass
7. Run QC check on a file with black frames: black_frames list populated
8. Create archive of a test workspace: archive contains expected files, manifest accurate
9. Open modified .kdenlive projects in Kdenlive: no parse errors, effects/compositions visible
