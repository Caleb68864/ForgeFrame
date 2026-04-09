---
date: 2026-04-08
updated: 2026-04-09
topic: "ForgeFrame Feature Roadmap"
author: Caleb Bennett
status: active
tags:
  - roadmap
  - planning
---

# ForgeFrame Feature Roadmap

## What's Built

### Phase 1 (Complete)
- Transcript generation (faster-whisper)
- Auto-marking (14 categories + phrase detection + repetition detection)
- Chapter generation
- Obsidian note CRUD with section-safe updates
- Review/selects timelines
- Kdenlive project adapter (parse/write/validate)
- Transitions + render pipeline
- 5 Production Brain skills (ff-prefixed)
- 21 MCP tools + 8 resources
- Full CLI with guided workflow

### Phase 2 (Complete)
- **ff-broll-whisperer** -- Smart B-roll suggestions from transcript (5 categories)
- **ff-pacing-meter** -- Segment-by-segment pacing analysis (WPM, energy drops, weak intros)
- **ff-pattern-brain** -- Extract MYOG build data (materials, measurements, steps, tips)
- **ff-voiceover-fixer** -- Rewrite rambling transcript segments into clean tutorial language
- **ff-auto-editor** -- Auto-assemble first-cut Kdenlive timeline from script + labeled clips
- **ff-audio-cleanup** -- Full audio pipeline (noise reduction, compression, de-esser, normalization)
- **ff-publish** -- YouTube publish assets (titles, description, tags, chapters, pinned comment)
- **ff-social-clips** -- Extract short-form clips for Shorts/Reels/TikTok
- **ff-youtube-analytics** -- Channel stats, video data, performance reports
- Build Replay Generator -- Auto-create condensed highlight timelines
- Title Card Generator -- Chapter title cards for Kdenlive
- B-Roll Library / Clip Organizer -- Tag and search clips across projects

### Current Stats
- 16 skills, 73 MCP tools, 21 pipelines
- 1,242 tests passing
- Python 3.12+

## Phase 3: Pipeline Completeness (Planned)

Gaps identified by comparing ForgeFrame capabilities against the video-editing-guide handbook pipeline. Ordered by impact.

### High Impact / Low Effort

1. **Capture Prep Skill** (`ff-capture-prep`)
   Generate pre-shoot checklist from shot plan: camera settings, mic setup, resolution/fps, lighting notes, sync strategy. Pure text skill, no new adapters.

2. **VFR Detection Tool** (`media_check_vfr`)
   Detect variable frame rate in ingested media, auto-suggest/run CFR transcode. FFprobe can detect this; FFmpeg adapter already exists.

3. **Full Render Tool** (`render_final`)
   Render with preset selection: youtube-1080p, youtube-4k, vimeo-hq, master-prores, master-dnxhr. Render profiles already exist in render/profiles.py -- needs user-facing MCP tool.

4. **QC Automation Tool** (`qc_check`)
   Post-render automated checks: black frame detection (ffmpeg blackdetect), audio clipping scan, loudness measurement, file size sanity check. All doable with existing FFmpeg adapter.

### Medium Effort / High Value

5. **Color Analysis + LUT Application** (`color_analyze`, `color_apply_lut`)
   Read histogram/waveform data from clips via ffprobe. Apply LUT files to clips in .kdenlive XML via filter elements. Kdenlive patcher can handle this.

6. **Effects Application Tool** (`effect_add`)
   Generic tool to add a named Kdenlive effect to a clip with parameters. The .kdenlive XML supports this via `<filter>` elements. Parser/serializer already handles the XML.

7. **Project Profile Setup** (`project_setup_profile`)
   Set Kdenlive project resolution/fps/color space in the .kdenlive file. XML attributes on `<profile>` element. Small but prevents downstream mistakes.

### Longer Term

8. **Compositing Tools** (`composite_pip`, `composite_wipe`)
   PiP layouts, composite-and-transform presets, wipe method selection. More complex -- compositing in Kdenlive involves `<transition>` elements with positioning.

9. **Project Archive Tool** (`project_archive`)
   Bundle workspace + renders + project file into dated archive. Supports "months later" editability goal from the handbook.

## Skip For Now
- **Tool-Aware Editing** -- Computer vision for tool detection. Requires CV models.
- **Experiment Engine** -- Multiple edit styles. Powerful but complex.
- **Multi-editor support** -- OTIO integration deferred while Kdenlive-only.
- **Speaker diarization** -- Solo creator = one speaker.
