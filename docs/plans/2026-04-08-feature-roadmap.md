---
date: 2026-04-08
updated: 2026-10-13
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

## Next Step: Kdenlive 26.08 Compatibility Fixes (2026-10-14)

Do this first, before the media MCP expansion phases
(`docs/plans/2026-10-13-media-mcp-expansion.md`). Evidence:
`docs/testing/2026-10-13-kdenlive-2608-differential.md` -- rendering the
`scripts/kdenlive_check_pack.py` projects with `kdenlive --render` (Kdenlive
26.08.2, headless) vs `melt` shows Kdenlive silently dropping generated content.

1. **Automate the differential.** A `requires_kdenlive` external test that
   builds the check pack, renders each project with `xvfb-run -a kdenlive
   --render` and with melt, and asserts matching frames/duration/audio
   (PSNR threshold, non-silent audio). Add a `requires_kdenlive` mark to
   `tests/_testkit.py`; optionally install Kdenlive in CI `full`.
2. **Audio is lost on insert.** `clip_insert` leaves `playlist_audio` empty and
   the video track has `hide="audio"`, so timelines are silent in both renderers.
   Place the A-side entry on the audio track; land `audio_fade` on it.
3. **Effects dropped by Kdenlive.** `effect_add` emits a bare
   `<filter mlt_service="avfilter.gblur">` inside the entry; Kdenlive 26.08
   discards it. Emit the full Kdenlive effect identity (`kdenlive_id`, etc. --
   see `vault/wiki/kdenlive-avfilter-and-effect-zones.md`).
4. ~~**Dissolves dropped by Kdenlive.**~~ **Done 2026-10-14.** Not dropped but
   hidden: the luma targeted the background (`a_track=0`) and was planted after
   the track compositors, and the left clip was stretched past its media. Now
   matches Kdenlive's own layout; Kdenlive and melt render the same dissolve.
   See `vault/wiki/kdenlive-cross-dissolve-pattern.md`.
5. **Hard-rule violations in generated XML:** a media clip gets `kdenlive:id` 3
   (reserved for the main sequence); `main_bin` entries have `out="0"`
   (need `length-1`); timeline `<entry>` elements lack `kdenlive:id`; the
   timewarp speed variant is registered in `main_bin` as its own clip.
6. **GUI pass.** Open `kdenlive-check-pack/*.kdenlive` in Kdenlive 26.08, record
   any load dialogs verbatim (`CHECKLIST.md`), save clean ones as native 26.08
   reference fixtures, then rewrite the CLAUDE.md "Hard rules" (still 25.x
   twin-chain wording) to the 26.x contract.
7. **Adopt `kdenlive --verify-file`** (Kdenlive master: headless load +
   `KdenliveDoc::checkConsistency()`) as a validator backend once it ships in a
   release.

Done when every check-pack step matches between Kdenlive and melt, audio is
audible, and the GUI pass shows no dialogs.

## Reliability and Guided Workflow (2026-10-13)

Execute these priorities in order. Independent research and implementation may
run in parallel; integrate dependencies in this order. Completion means the
behavior is available through documented user entry points, not only helpers.

1. **Unify preview and final rendering** — implemented, runtime validation pending. Use one executor and
   artifact registry; preserve rational frame rates, honor profile containers,
   verify output streams/duration, clean partial outputs, and render originals
   rather than proxies for full-quality exports.
2. **Validate serialized Kdenlive XML** — implemented, compatibility follow-up below. Check the emitted
   document before writes, with actionable errors for identity, references,
   producer ranges, track structure, and the supported document shapes.
3. **Persistent jobs for long operations** — implemented, runtime validation pending. Return job IDs immediately
   for render, proxy generation, and transcription; persist status/progress/logs,
   support cancellation, and expose recovery after restart.
4. **Central safe file writes** — implemented, runtime validation pending. Share resolved protected-path checks,
   mandatory snapshots before project replacement, validation, atomic writes,
   and concurrency protection across project/manifest/registry writes.
5. **Capability discovery and installation** — implemented, runtime validation pending. Generate the tool/skill
   catalog from implementation metadata, align both package extras, refresh
   installation guidance, and add `wvb doctor` for binaries, encoders, effects,
   optional engines, and model readiness.
6. **Guided project workflow** — implemented, runtime validation pending. Report readiness, missing artifacts,
   and the next action; offer a resumable footage → selects → assembly → preview
   → review workflow that pins project versions and explains clip choices.

### Implementation notes and follow-up

- Both render paths now use the executor and artifact registry. Rational rates,
  profile containers/muxers, original-media selection, output verification,
  failed-output cleanup, and unique filenames are shared.
- XML checks run against the final tree and staged file before replacement.
  **Compatibility remains unresolved:** `AGENTS.md` requires Kdenlive 25.x twin
  chains, but the existing serializer and `tests/unit/test_serializer_eshape.py`
  describe the GUI-confirmed Kdenlive 26.04 E shape (single media producers and
  different bin identity rules). This change preserves existing output and
  validates rules appropriate to each detected shape; it does not establish
  25.x conformance. Confirm the supported version and reconcile the contract
  with native fixtures before a format migration.
- `wvb jobs submit/list/status/cancel/retry` and equivalent MCP tools persist
  detached render/proxy/transcription/workflow operations in SQLite. Currently
  Linux/macOS only; one detached writer per workspace. Progress describes stages
  and assets, rather than frame-level render percentages. Synchronous APIs remain
  available and must not be used concurrently to mutate the same workspace.
  Restarted workers are reconciled on job inspection; interrupted jobs require
  explicit retry, and live orphan children prevent unsafe reuse of outputs.
- Project writes, version allocation, manifests, restores, render registry, and
  new workflow reports share resolved path guards and atomic write/lock support.
  Existing project replacement aborts if snapshot creation fails.
- `wvb doctor`, `wvb capabilities`, and corresponding MCP tools expose host
  availability and registration metadata. All four extras match both package
  roots and both dependency lockfiles have been regenerated.
  `docs/capabilities.md` is generated; regenerate when tools/skills change.
- `wvb project-status` and `wvb workflow --through review` expose resumable,
  version-pinned first cuts with clip-selection explanations. The initial
  workflow expects speech transcripts and script steps in `reports/script.json`;
  silent footage still needs manual planning. Review prepares a checklist and
  leaves editorial approval to the creator.

Validation performed: static source review, Python syntax parsing, generated
capability documentation, and whitespace checks. No tests were added or run.
Next validation work: update mocks for unified rendering; exercise focused
render/XML/job/workflow checks; then run the full suite and open generated
projects in the supported Kdenlive version.

## Skip For Now
- **Tool-Aware Editing** -- Computer vision for tool detection. Requires CV models.
- **Experiment Engine** -- Multiple edit styles. Powerful but complex.
- **Multi-editor support** -- OTIO integration deferred while Kdenlive-only.
- **Speaker diarization** -- Solo creator = one speaker.
