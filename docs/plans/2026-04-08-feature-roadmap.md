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

Status check 2026-11-09: all four items below were already implemented in
`43b02c5` (2026-04-09, "Phase 3 Pipeline Completeness"). Verified against the
code on branch `wip/2026-11-09-phase3`; hardening fixes noted per item.

1. ~~**Capture Prep Skill** (`ff-capture-prep`)~~ **Done (`43b02c5`).**
   Generate pre-shoot checklist from shot plan: camera settings, mic setup, resolution/fps, lighting notes, sync strategy. Pure text skill, no new adapters.
   Skill `workshop-video-brain/skills/ff-capture-prep/SKILL.md`, generator
   `production_brain/skills/capture_prep.py::generate_capture_checklist`,
   tests `tests/unit/test_capture_prep.py`.

2. ~~**VFR Detection Tool** (`media_check_vfr`)~~ **Done (`43b02c5`).**
   Detect variable frame rate in ingested media, auto-suggest/run CFR transcode. FFprobe can detect this; FFmpeg adapter already exists.
   `media_check_vfr` + `media_transcode_cfr` in `edit_mcp/server/tools/workspace_media.py`,
   pipeline `edit_mcp/pipelines/vfr_check.py`, tests `tests/unit/test_vfr_check.py`.
   Fixed 2026-11-09: every VFR entry reported `r_frame_rate`/`avg_frame_rate`
   `"0/1"` and 0% divergence, because `MediaAsset` had no such fields and the
   pipeline read them with a `getattr` default; probe now records both. A file
   that failed to probe was dropped silently and the report still said
   `all_cfr=True` (even with ffprobe missing); it is now listed in
   `unprobed_files` and `all_cfr` is false. Each VFR entry carries a
   `suggested_action` (the `media_transcode_cfr` call). Real-ffprobe proof:
   `tests/integration/test_vfr_check_real_ffprobe.py`.

3. ~~**Full Render Tool** (`render_final`)~~ **Done (`43b02c5`).**
   Render with preset selection: youtube-1080p, youtube-4k, vimeo-hq, master-prores, master-dnxhr. Render profiles already exist in render/profiles.py -- needs user-facing MCP tool.
   `render_final_tool` + `render_list_profiles` in `edit_mcp/server/tools/render.py`,
   pipeline `edit_mcp/pipelines/render_final.py` (shared executor since the
   Reliability work); all five presets present in `adapters/render/profiles.py`.

4. ~~**QC Automation Tool** (`qc_check`)~~ **Done (`43b02c5`); hardened 2026-11-09.**
   Post-render automated checks: black frame detection (ffmpeg blackdetect), audio clipping scan, loudness measurement, file size sanity check. All doable with existing FFmpeg adapter.
   `qc_check` in `edit_mcp/server/tools/render.py`, pipeline `edit_mcp/pipelines/qc_check.py`.
   Fixed 2026-11-09: the clipping check searched stderr for `Flat_factor`,
   which astats never prints, so it could not fire on real audio (the unit
   fixture was invented text). It now parses astats `Peak level dB` and
   `Flat factor`. ffmpeg exit codes were ignored, so a corrupt file or a
   video-only render "passed" silence/clipping; non-zero exits are now skips
   with a reason in `check_errors`. `overall_pass` is false when every check
   was skipped, a missing file's `file_size` is a skip rather than a pass, and
   unknown check names are rejected (`invalid_input`) instead of skipped
   silently. Real-ffmpeg proof: `tests/integration/test_qc_check_real_ffmpeg.py`.

#### Open follow-ups found 2026-11-09

- **QC silence threshold vs. tutorials.** `_check_silence` fails any render
  with a single 1 s gap below -50 dB, which flags deliberate pauses in normal
  tutorial footage. Consider a minimum-duration or percentage threshold
  (`edit_mcp/pipelines/qc_check.py::_check_silence`).
- **QC loudness only checks "too quiet".** `_check_loudness` fails below
  -24 LUFS or above -1 dBTP; it does not report distance from the YouTube
  -14 LUFS target or flag an over-loud master
  (`edit_mcp/pipelines/qc_check.py::_check_loudness`).
- **QC is not profile-aware.** `qc_check` takes only a file, so it cannot check
  the render matches the requested profile (resolution, fps, codec). The
  executor already verifies streams/duration; QC could reuse the profile
  (`edit_mcp/server/tools/render.py::qc_check`).

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

1. **Automate the differential.** **Done** (`5724bb7`, 21 cases, all passing 2026-11-02). A `requires_kdenlive` external test that
   builds the check pack, renders each project with `xvfb-run -a kdenlive
   --render` and with melt, and asserts matching frames/duration/audio
   (PSNR threshold, non-silent audio). Add a `requires_kdenlive` mark to
   `tests/_testkit.py`; optionally install Kdenlive in CI `full`.
2. **Audio is lost on insert.** **Done 2026-10-14.** `clip_insert` now places
   audio-bearing media on the first audio playlist at the same timeline frame,
   and reports the target and placement status. Speed and dissolve edits keep
   paired starts aligned; `audio_fade` targets the audio entry and emits
   Kdenlive's native fade identity. **Completed 2026-11-02:** the render proof that
   was blocked in October showed Kdenlive still silent (-91 dB). Audio tracks now
   carry `kdenlive:audio_track=1`, and a speed clip gets one producer per track.
   Kdenlive and melt both measure -24.1 dB and all 21 differential cases pass.
   Other move/trim intents are still known sync gaps.
3. **Effects dropped by Kdenlive.** **Done 2026-10-14; render-verified 2026-11-02 (PSNR 36.65, edge energy 0.72 -> 0.50).** A missing `kdenlive_id` makes Kdenlive drop a clip filter; an unknown id aborts `kdenlive --render`; the effect XML file name is not the registry id. The `effect_identity.normalize_effect_id` resolver and serializer safety net normalize known ids and remove unknown ones. See `vault/wiki/kdenlive-avfilter-and-effect-zones.md`.
4. ~~**Dissolves dropped by Kdenlive.**~~ **Done 2026-10-14.** Not dropped but
   hidden: the luma targeted the background (`a_track=0`) and was planted after
   the track compositors, and the left clip was stretched past its media. Now
   matches Kdenlive's own layout; Kdenlive and melt render the same dissolve.
   See `vault/wiki/kdenlive-cross-dissolve-pattern.md`.
5. ~~**Hard-rule violations in generated XML:** media and sequence IDs collide
   with reserved IDs, media `main_bin` entries have `out="0"`, timeline entries
   lack IDs, and speed variants appear in the bin.~~ **Done 2026-10-14.** IDs,
   effective lengths, and timeline entry IDs now follow the native pattern.
   Speed and timeremap variants share their source ID and stay out of `main_bin`.
6. **GUI pass.** Open `kdenlive-check-pack/*.kdenlive` in Kdenlive 26.08, record
   any load dialogs verbatim (`CHECKLIST.md`), save clean ones as native 26.08
   reference fixtures, then rewrite the CLAUDE.md "Hard rules" (still 25.x
   twin-chain wording) to the 26.x contract.
7. **Adopt `kdenlive --verify-file`** (Kdenlive master: headless load +
   `KdenliveDoc::checkConsistency()`) as a validator backend once it ships in a
   release. Checked 2026-11-02: Kdenlive 26.08.2 lacks the flag, so this stays parked.

Done when every check-pack step matches between Kdenlive and melt, audio is
audible, and the GUI pass shows no dialogs.

## Reliability and Guided Workflow (2026-10-13)

Execute these priorities in order. Independent research and implementation may
run in parallel; integrate dependencies in this order. Completion means the
behavior is available through documented user entry points, not only helpers.

1. **Unify preview and final rendering** — implemented, validated 2026-11-02. Use one executor and
   artifact registry; preserve rational frame rates, honor profile containers,
   verify output streams/duration, clean partial outputs, and render originals
   rather than proxies for full-quality exports.
2. **Validate serialized Kdenlive XML** — implemented, compatibility follow-up below. Check the emitted
   document before writes, with actionable errors for identity, references,
   producer ranges, track structure, and the supported document shapes.
3. **Persistent jobs for long operations** — implemented, validated 2026-11-02. Return job IDs immediately
   for render, proxy generation, and transcription; persist status/progress/logs,
   support cancellation, and expose recovery after restart.
4. **Central safe file writes** — implemented, validated 2026-11-02. Share resolved protected-path checks,
   mandatory snapshots before project replacement, validation, atomic writes,
   and concurrency protection across project/manifest/registry writes.
5. **Capability discovery and installation** — implemented, validated 2026-11-02. Generate the tool/skill
   catalog from implementation metadata, align both package extras, refresh
   installation guidance, and add `wvb doctor` for binaries, encoders, effects,
   optional engines, and model readiness.
6. **Guided project workflow** — implemented, validated 2026-11-02. Report readiness, missing artifacts,
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

Validation 2026-11-02: every CLI and job entry point was run on a synthetic
workspace; see `docs/testing/2026-11-02-reliability-runtime-validation.md`.
`tests/integration/test_reliability_cli.py` (8 cases) now covers the CLI, a real
render job, and cancelling a running render with a real worker. Limits that remain:
detached jobs are POSIX only, progress is per stage rather than per frame, and
opening generated projects in the Kdenlive GUI is still outstanding (prompt 06).

## Skip For Now
- **Tool-Aware Editing** -- Computer vision for tool detection. Requires CV models.
- **Experiment Engine** -- Multiple edit styles. Powerful but complex.
- **Multi-editor support** -- OTIO integration deferred while Kdenlive-only.
- **Speaker diarization** -- Solo creator = one speaker.
