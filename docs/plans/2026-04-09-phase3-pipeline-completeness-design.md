---
date: 2026-04-09
topic: "Phase 3 Pipeline Completeness -- 9 Features"
author: Caleb Bennett
status: draft
tags:
  - design
  - phase3
  - pipeline-completeness
---

# Phase 3 Pipeline Completeness -- Design

## Summary

Nine features that close every gap between the video-editing-guide handbook pipeline and ForgeFrame's actual capabilities. Uses a hybrid approach: build 3 shared infrastructure pieces first (extended FFprobe, Kdenlive filter insertion engine, render profile expansion), then 9 vertical feature slices in priority order. All features follow existing codebase patterns (model -> pipeline -> MCP tool -> optional skill).

## Approach Selected

**Approach C: Hybrid (Infrastructure First, Then Vertical Slices)** -- Features 2/4/5 share FFprobe extensions, features 5/6/8 share Kdenlive filter insertion, feature 3 needs render profile expansion. Building infrastructure first prevents rework and makes slices fast.

## Architecture

```
INFRASTRUCTURE LAYER (build first)
├── FFprobe Extended (probe.py)
│   - VFR detection (r_frame_rate vs avg_frame_rate divergence >5%)
│   - Color metadata (color_space, color_primaries, color_transfer)
│   - Post-render loudness measurement
│   Used by: features 2, 4, 5
│
├── Kdenlive Filter Insertion Engine (patcher.py)
│   - AddEffect intent -> <filter> element on clip/track
│   - AddComposition intent -> <transition> for compositing
│   Used by: features 5, 6, 8
│
└── Render Profile Expansion (profiles.py + YAML)
    - 5 new presets: youtube-1080p, youtube-4k, vimeo-hq, master-prores, master-dnxhr
    - Fast Start (movflags +faststart) flag support
    Used by: feature 3

FEATURE SLICES (priority order)
1. Capture Prep (skill only)
2. VFR Detection (ffprobe + ffmpeg transcode)
3. Full Render (render profiles + executor)
4. QC Automation (ffmpeg blackdetect/silencedetect + probe)
5. Color/LUT (probe color + filter insertion)
6. Effects Application (filter insertion)
7. Project Profile Setup (serializer XML attrs)
8. Compositing Tools (composition insertion)
9. Project Archive (tarfile/zipfile)
```

## Components

### Infrastructure

| Component | Owns | Does NOT Own |
|-----------|------|-------------|
| FFprobe Extended (probe.py) | VFR detection, color metadata extraction, stream-level analysis | Transcoding, rendering, file mutations |
| Kdenlive Filter Engine (patcher.py + new intents) | Inserting `<filter>` and `<transition>` XML into parsed projects | Effect parameter discovery, UI preview, rendering |
| Render Profile Expansion (profiles.py + YAML) | Preset definitions, codec/bitrate/flag combinations | FFmpeg execution (executor.py), file I/O |

### Features

| # | Feature | New Files | Extends |
|---|---------|-----------|---------|
| 1 | Capture Prep | `skills/ff-capture-prep/SKILL.md`, `production_brain/skills/capture_prep.py` | Nothing -- pure skill |
| 2 | VFR Detection | `pipelines/vfr_check.py`, `core/models/media_check.py` | `probe.py` (VFR fields on MediaAsset) |
| 3 | Full Render | `pipelines/render_final.py` | `profiles.py` (new YAMLs), `executor.py` (fast-start) |
| 4 | QC Check | `pipelines/qc_check.py`, `core/models/qc.py` | `probe.py` (loudness), FFmpeg filters |
| 5 | Color/LUT | `pipelines/color_tools.py`, `core/models/color.py` | `probe.py` (color metadata), `patcher.py` (AddEffect) |
| 6 | Effect Add | `pipelines/effect_apply.py` | `patcher.py` (AddEffect -- shared with #5) |
| 7 | Project Profile | `pipelines/project_profile.py` | `serializer.py` (profile XML attributes) |
| 8 | Compositing | `pipelines/compositing.py`, `core/models/compositing.py` | `patcher.py` (AddComposition) |
| 9 | Archive | `pipelines/archive.py`, `core/models/archive.py` | Nothing -- tarfile/zipfile |

## Data Flow

```
Raw media -> FFprobe Extended -> MediaAsset (+ is_vfr, color_space, color_primaries)
                                     |
                            VFR Check pipeline (uses VFR flag)
                            QC Check pipeline (uses loudness + color)
                            Color Tools pipeline (uses color metadata)

.kdenlive XML -> Parser -> KdenliveProject
                               |
                     Patcher + AddEffect -> modified project (color/LUT/effects)
                     Patcher + AddComposition -> modified project (PiP/wipes)
                     Serializer (profile attrs) -> modified project (resolution/fps)

Render Profile YAML -> load_profile() -> RenderProfile
                                             |
                                     render_final -> FFmpeg executor -> output file
                                                             |
                                                     QC Check -> QCReport
```

### Key Models

- `MediaAsset` (extended): adds `is_vfr: bool`, `color_space: str | None`, `color_primaries: str | None`
- `AddEffect` intent: `track_index`, `clip_index`, `effect_name`, `params: dict` -> `<filter>` XML
- `AddComposition` intent: `track_a`, `track_b`, `composition_type`, `params: dict` -> `<transition>` XML
- `QCReport`: `black_frames: list[TimeRange]`, `audio_clipping: bool`, `loudness_lufs: float`, `file_size_bytes: int`, `passed: bool`
- `ColorAnalysis`: `color_space: str`, `luminance_range: tuple`, `has_clipping: bool`, `histogram_data: dict`
- `ArchiveManifest`: `workspace_path`, `render_paths: list`, `project_path`, `archive_path`, `created_at`, `size_bytes`

## Error Handling

1. **VFR detection false positives**: Use >5% divergence threshold between r_frame_rate and avg_frame_rate. Some CFR files have metadata drift.

2. **Missing FFmpeg filters for QC**: blackdetect/silencedetect require specific builds. If filter unavailable, skip that check and note in QCReport. Never fail whole pipeline for one missing filter.

3. **Kdenlive effect names vary by build**: Accept raw filter names in effect_add. Don't validate against hardcoded list. Let Kdenlive handle unknown effects at render time.

4. **ProRes/DNxHR codec unavailability**: Check codec availability via `ffmpeg -codecs` before render. Return clear error if missing encoder.

5. **Archive of large workspaces**: Stream to tar/zip rather than loading into memory. Report progress for large archives.

Pattern: Per-item try-catch, log warnings, add to report errors list. Never fail whole pipeline for one bad item. Consistent with existing codebase convention.

## Open Questions

1. **VFR transcode as separate tool or integrated?** -> Decision: Separate tool (`media_transcode_cfr`). Detection and action decoupled so user can decide.

2. **Archive format?** -> Decision: tar.gz default (better compression, Linux-first), zip option for cross-platform.

3. **Should capture-prep read shot plan from workspace?** -> Decision: Yes, read from workspace (consistent with other skills).

## Approaches Considered

**Approach A: Bottom-Up Layers** -- Build all adapters, then all pipelines, then all tools. Maximum consistency but nothing user-facing until late. Rejected: too slow to deliver value.

**Approach B: Vertical Slices** -- Each feature as complete slice in priority order. Immediately usable but may discover shared infrastructure needs late (6 of 9 features share infra). Rejected: rework risk.

**Approach C: Hybrid (Selected)** -- Infrastructure first, then vertical slices. Gets hardest architectural work done early, slices are fast because infra exists. Best fit for this project.

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-04-09-phase3-pipeline-completeness-design.md`)
- [ ] Run forge-prep to expand sub-specs
- [ ] Execute via forge-run
