---
date: 2026-07-14
topic: "ForgeFrame Visual Research and Media Intelligence Expansion"
author: Caleb Bennett
status: evaluated
evaluated_date: 2026-07-14
tags:
  - design
  - forgeframe-visual-research-media-intelligence
  - visual-research
  - media-analysis
---

# ForgeFrame Visual Research and Media Intelligence — Design

## Summary

Add a transcript-guided visual-research capability to ForgeFrame: given a video, an
existing transcript, and optionally a query / topic list / timestamp range, produce a
compact, deduplicated set of high-quality timestamped screenshots plus a structured
manifest — usable by a human, a CLI, or an external AI agent without hand-writing FFmpeg.

The system is built as a **new `visual_research` capability layered onto ForgeFrame's
existing primitives**, not a parallel stack. It reuses the FFmpeg runner, the
ffprobe→`MediaAsset` model, the `TranscriptSegment` model, the whisper engine, the
Click CLI, the FastMCP tool surface, and the Obsidian note writer. Only genuinely-absent
pieces are new: a transcript *repository* (loading/searching SRT/VTT/JSON), frame
extraction, scene detection, candidate generation, local quality scoring, perceptual
deduplication, optional OCR/vision providers, and the research manifest/export.

All AI is optional and behind provider abstractions; the deterministic core runs fully
local with zero AI configured.

## Approach Selected

**Approach B — Extend the existing `edit_mcp` convention (adapters + pipelines +
core/models).** Rationale: ForgeFrame already has a clean three-layer shape (typed models
in `core/models`, external-tool wrappers in `edit_mcp/adapters`, orchestration in
`edit_mcp/pipelines`, surfaced through Click CLI + FastMCP tools). The spec's proposed
top-level `forgeframe/{core,transcript,visual_research}` package is greenfield-shaped and
would fork that convention. Mapping the spec onto the existing layers keeps one FFmpeg
execution path, one config system, one model package, and one test layout — which is
exactly the spec's stated non-negotiable ("do not create a duplicate FFmpeg execution
system", "prefer extending and consolidating over parallel implementations").

## Design Forks Resolved (autonomous decisions)

These four repo-specific decisions were made with best judgement in autonomous mode. Each
is reversible; rationale is recorded so `/forge` and red-team can challenge them.

### Fork 1 — Module placement: follow existing `edit_mcp` convention (not a new top-level package)

- **Models** → `core/models/visual_research.py`: `ResearchQuery`, `ResearchRegion`,
  `FrameCandidate`, `FrameVisualMetrics`, `ResearchCapture`, `ResearchManifest`,
  `FrameEvaluation`. Reuse `MediaAsset` (as the source model) and `TranscriptSegment`.
- **Adapters** (wrap external tools) →
  - `edit_mcp/adapters/ffmpeg/frames.py` — exact/burst/centered frame extraction.
  - `edit_mcp/adapters/ffmpeg/scene.py` — FFmpeg scene-change detection.
  - `edit_mcp/adapters/transcript/parsers.py` — SRT/VTT/JSON → `TranscriptSegment[]`.
  - `edit_mcp/adapters/ocr/` — optional OCR provider interface + local (tesseract) impl.
  - `edit_mcp/adapters/vision/` — optional vision-evaluator interface + local fallback.
- **Pipelines / services** (orchestration) →
  - `edit_mcp/pipelines/transcript_repository.py` — load/query/slice/search transcripts.
  - `edit_mcp/pipelines/visual_research/` — `service.py`, `regions.py`, `candidates.py`,
    `scoring.py`, `dedup.py`, `export.py`.
- **Surfaces** → new Click commands in `app/cli.py`; new tools registered in
  `edit_mcp/server/tools.py`.

**Reason:** matches the pattern every existing feature already follows (e.g. `ingest`,
`pacing_analyzer`, `clip_search`). New contributors and existing tests stay in one mental
model. Rejected: a top-level `forgeframe/` package (parallel-stack risk) and a standalone
daemon/microservice (over-engineered for a local-first CLI; see Approach C).

### Fork 2 — Config: a Pydantic `ResearchConfig` model, no new YAML-file mechanism

- Add a `ResearchConfig` Pydantic model (nested groups mirroring the spec's YAML shape:
  windowing, candidate_generation, scene_detection, quality, deduplication, ocr, vision,
  export) with class-level defaults.
- Precedence: **explicit call args / CLI flags > `WVB_*` env vars (for a few top-level
  toggles) > `ResearchConfig` defaults.**
- The existing env-var `Config` dataclass (`app/config.py`) stays the entry point and
  gains ffmpeg/whisper/tesseract availability checks; `ResearchConfig` is passed into the
  service and is fully serializable into the manifest's sanitized `configuration` block.

**Reason:** the repo has **no file-based config loader today** — config is env vars +
per-call arguments. Introducing a YAML config file *just* for visual research would be
the "second incompatible configuration mechanism" the spec forbids. `pyyaml` is already a
dependency, so a file layer can be added later without new deps if a real need appears;
this design deliberately defers it. Defaults live in code, overrides are explicit.

### Fork 3 — Image analysis: FFmpeg-first, then numpy + Pillow; **not** OpenCV

- **Free-from-FFmpeg metrics** (no Python image lib): brightness / black-frame /
  overexposure via `signalstats` + `blackdetect`/`blackframe`; scene-difference score via
  the scene filter. Computed during extraction where possible.
- **Pixel-level metrics** (sharpness = variance-of-Laplacian, entropy, perceptual hashes
  pHash/dHash, optional SSIM): **numpy + Pillow**, hand-rolled. Both ship Windows wheels
  and install cleanly on the user's primary OS.
- **Reject OpenCV**: heavy, slow Windows install story, and unnecessary for these metrics.
- All scoring/dedup is **optional and gated** behind a `FrameScorer` interface; if
  numpy/Pillow are absent, core extraction + export still work (scoring degrades to
  FFmpeg-only metrics or is skipped, logged clearly).

**Reason:** honors "reuse the FFmpeg foundation" and "avoid adding a large dependency
unnecessarily", keeps the dependency surface to two ubiquitous wheels, and keeps a swap
point for an OpenCV backend later behind the interface.

### Fork 4 — Design depth: fully specify the deterministic core (phases 1–3); AI + agent as interface contracts (phase 4–5)

- Phases 1–3 (primitives, region→candidate→select pipeline, manifest/export/Obsidian) are
  specified concretely below.
- Phases 4–5 (vision provider, external-agent candidate handshake, OCR provider, caching,
  resumability) are specified as **stable interface + data contracts and cache-key
  definitions**, deliberately not fleshed to line level — matching the spec's own "keep
  behind an abstraction, never a core requirement."

**Reason:** correctness and reuse risk lives in the deterministic core, which `/forge`
will build first. Nailing the AI/agent *contracts* (not implementations) is what protects
the AI-optional boundary; detailing an implementation now would over-commit.

## Architecture

Three existing layers, extended. Data flows top→bottom; nothing below calls anything
above it.

```
                 ┌────────────────────────────────────────────────────────────┐
 Surfaces        │  Click CLI (app/cli.py)      FastMCP tools (server/tools.py)│
                 │   research / frame / scenes / transcript                    │
                 └───────────────┬───────────────────────────┬────────────────┘
                                 │  ResearchQuery / flags     │  JSON in/out
                                 ▼                            ▼
 Orchestration   ┌────────────────────────────────────────────────────────────┐
 (pipelines/)    │  visual_research/service.py  ── research_video() pipeline   │
                 │    regions.py → candidates.py → scoring.py → dedup.py        │
                 │                → (ocr) → (vision) → select → export.py       │
                 │  transcript_repository.py  (load / query / slice / search)   │
                 └───┬───────────────┬───────────────┬──────────────┬──────────┘
                     ▼               ▼               ▼              ▼
 Adapters        ┌────────┐   ┌───────────┐   ┌──────────┐   ┌──────────────┐
 (adapters/)     │ffmpeg/ │   │ffmpeg/    │   │transcript│   │ ocr/  vision/│  (optional)
                 │frames  │   │scene probe│   │/parsers  │   │ providers    │
                 │runner  │   │           │   │          │   │ + local      │
                 └────┬───┘   └─────┬─────┘   └────┬─────┘   └──────┬───────┘
                      ▼             ▼              ▼                ▼
 Models          ┌────────────────────────────────────────────────────────────┐
 (core/models/)  │ MediaAsset (reused)   TranscriptSegment (reused/extended)   │
                 │ visual_research.py: ResearchQuery/Region/FrameCandidate/     │
                 │                     ResearchCapture/ResearchManifest         │
                 └────────────────────────────────────────────────────────────┘
```

**Key interaction:** `service.research_video()` is the single orchestration entry point.
Every stage is an independently-callable function taking + returning typed models, so the
CLI `frame`/`scenes`/`transcript` commands and future MCP tools call individual stages
directly, and an external agent can drive stage-by-stage.

## Components

### Reused (do not reimplement)

- **`adapters/ffmpeg/runner.py::run_ffmpeg`** — owns FFmpeg subprocess execution, timeout,
  structured `FFmpegResult`. *Gap:* it always emits `-y -i <input> <args> <output>` (input
  before args), so it can't place `-ss` before `-i` for fast seek. Frame extraction needs
  a pre-input arg path — see `frames.py` below (extends the runner; does **not** fork it).
- **`adapters/ffmpeg/probe.py::probe_media` → `MediaAsset`** — owns media metadata. This is
  the spec's `MediaSource`. Reused as-is.
- **`core/models/transcript.py::TranscriptSegment`** — reused; **extended** with optional
  `segment_id`, `speaker`, `tags`, `metadata` (additive, backward-compatible).
- **`adapters/stt/whisper_engine.py`** — owns transcript *generation*. Unchanged; the new
  repository only *consumes* transcripts.
- **`production_brain/notes/writer.py`** — owns Obsidian note writing (section-safe,
  frontmatter-merge). The export stage calls it; no parallel Obsidian implementation.
- **`app/cli.py`, `edit_mcp/server/tools.py`** — the two surfaces; extended, not replaced.

### New

- **`transcript_repository.py`** — owns: normalize SRT/VTT/JSON/existing-format into
  `TranscriptSegment[]`; keyword search; segments overlapping a time range; ±N-second
  context around a timestamp; merge adjacent segments. Owns loading/querying only —
  **not** generation (that stays in whisper_engine).
- **`adapters/ffmpeg/frames.py`** — owns exact frame extraction (`extract_frame`), burst
  (`extract_frame_burst`), and centered burst (`extract_centered_burst`). Owns the
  fast-vs-accurate seek tradeoff and PNG/JPEG output. Returns `FrameCandidate`s. Records
  the *actual* extracted timestamp when it differs from requested.
  - **Reuses `run_ffmpeg`, does not fork it.** The runner is refactored to accept an
    optional `pre_input_args: list[str]` (backward compatible; default `[]`) so `-ss`
    can be placed *before* `-i` for fast seek. This keeps a single FFmpeg execution path
    (the spec's hard constraint).
  - **Accurate-seek default for research quality:** default extraction uses accurate
    seek (`-ss` after `-i`, or a two-step coarse+accurate seek) so the returned frame
    truly corresponds to the requested timestamp; a `quality="fast"` mode uses pre-input
    seek. On **VFR sources** (checked via the reused `MediaAsset.is_vfr`), fast seek is
    unreliable — the extractor forces accurate seek and records a `vfr_warning` in
    candidate metadata (and the manifest), optionally suggesting the existing
    `media_transcode_cfr` step. This closes the repo's known VFR trap.
- **`adapters/ffmpeg/scene.py`** — owns `detect_scene_changes` via FFmpeg
  `select='gt(scene,threshold)',showinfo` + `pts_time` parsing from stderr. Owns threshold,
  time-range restriction, minimum-gap enforcement, and the uniform-sampling fallback when
  no scenes are found. Owns nothing about *which* scenes matter.
- **`adapters/transcript/parsers.py`** — owns format detection + parsing to segments.
- **`visual_research/regions.py`** — owns turning transcript matches / explicit segment IDs
  / timestamp lists / (optional) AI suggestions into bounded `ResearchRegion`s: expand by
  pre/post-roll, cap at max region seconds, merge near-adjacent. Owns the windowing rules.
- **`visual_research/candidates.py`** — owns adaptive candidate generation per region
  (anchor + uniform burst + scene changes), and the raw-candidate cap.
- **`visual_research/scoring.py`** — owns local quality metrics (sharpness, brightness,
  entropy, text-density, visual-change) behind a `FrameScorer` interface, configurable
  weights, and per-mode profiles (software_ui / slide_deck / physical_demo). Metrics stay
  independently inspectable on the candidate — never collapsed into one opaque number.
- **`visual_research/dedup.py`** — owns perceptual dedup within a region and optionally
  across final captures; preserves the highest-ranked of a duplicate cluster; records
  duplicate relationships in debug metadata; never deletes candidate images mid-run.
- **`visual_research/service.py`** — owns the end-to-end `research_video()` pipeline,
  stage enable/disable, per-region error isolation, and manifest assembly.
- **`visual_research/export.py`** — owns manifest.json, index.md, screenshot filename
  generation (zero-padded + safe slug + collision handling), and Obsidian output modes.
- **`adapters/ocr/` and `adapters/vision/`** — own the *optional* provider interfaces and
  local fallbacks. Never imported on the core path.

## Data Flow

`research_video(source, transcript?, query?, topics?, timestamp_ranges?, config?) -> ResearchManifest`

1. **Probe** — `probe_media(source)` → `MediaAsset`. Fail fast with `MediaProbeError`.
2. **Resolve transcript** — if a transcript path is supplied, `transcript_repository`
   loads + normalizes it; if absent and `--transcribe` is set, call `whisper_engine`;
   otherwise proceed transcript-free (visual-only regions from scene detection).
3. **Determine regions** — `regions.py` builds `ResearchRegion[]` from the query/topics
   (keyword search over the repository), explicit timestamps/ranges, and/or scene changes.
   AI region suggestions, if enabled, are treated as *suggestions* and passed through the
   same deterministic windowing — never trusted as final.
4. **Generate candidates** — for each region, `candidates.py` produces `FrameCandidate`s
   (anchor near transcript time, uniform burst, scene changes), extracted via
   `frames.py`, capped at `max_raw_candidates`.
5. **Score locally** — `scoring.py` fills `FrameVisualMetrics` (FFmpeg-cheap metrics
   always; numpy/Pillow metrics if available), drops invalid/black/blurred, keeps top
   `max_filtered_candidates`.
6. **OCR (optional)** — if enabled, annotate candidates with `ocr_text`.
7. **Deduplicate** — `dedup.py` collapses near-identical candidates per region.
8. **Vision rank (optional)** — send ≤ `max_vision_candidates` to the configured
   `VisionFrameEvaluator`; on any failure, fall back to local ranking.
9. **Select** — deterministic default picks the top candidate per region (or per concept);
   external-agent mode instead returns the candidate manifest and accepts selected IDs.
10. **Export** — `export.py` copies selected frames to `screenshots/`, writes
    `manifest.json` + `index.md`, and (if requested) Obsidian notes via the notes writer.
11. **Return** `ResearchManifest`. Per-region failures are recorded in the manifest, not
    fatal (see Error Handling).

Canonical timestamp representation throughout: **float seconds**; human formatting
`HH:MM:SS.mmm` at the edges only. Resource paths normalized to forward slashes in
manifests (consistent with the existing Kdenlive serializer rule).

## Domain Models (core/models/visual_research.py)

- `ResearchQuery(query?, topics[], source_id, start_seconds?, end_seconds?, max_results,
  include_visual_only_regions, transcript_required, metadata)`
- `ResearchRegion(region_id, start_seconds, end_seconds, anchor_seconds?,
  transcript_segment_ids[], transcript_excerpt, topics[], relevance_score?, reason,
  source_method∈{transcript,query,scene_change,manual_timestamp,chapter,marker,external_agent},
  metadata)`
- `FrameVisualMetrics(sharpness?, brightness?, entropy?, text_density?,
  scene_difference?, perceptual_hash?, ocr_text?, ai_score?, ai_reason?)`
- `FrameCandidate(candidate_id, source_id, region_id?, timestamp_seconds, image_path,
  width, height, extraction_method∈{exact_timestamp,uniform_burst,scene_change,adaptive,manual},
  metrics: FrameVisualMetrics, metadata)`
- `ResearchCapture(capture_id, source_id, region_id?, selected_candidate_id, image_path,
  timestamp_seconds, transcript_excerpt?, title, slug, description?, selection_reason,
  topics[], ocr_text?, source_filename, metadata)`
- `ResearchManifest(manifest_version, generated_at, source: MediaAsset, query?: ResearchQuery,
  regions[], captures[], processing{ffmpeg_version?, transcript_provider?, vision_provider?,
  ocr_provider?, configuration})`
- `FrameEvaluation(candidate_id, relevance_score, clarity_score, completeness_score,
  text_readability_score?, overall_score, reason)` — vision provider output.

All extend the repo's `SerializableMixin`. `source_id` is the `MediaAsset` hash/id, keeping
one identity scheme.

## Error Handling

Follow existing conventions; add typed exceptions: `MediaNotFoundError`,
`FFmpegUnavailableError`, `MediaProbeError`, `TranscriptLoadError`, `FrameExtractionError`,
`SceneDetectionError`, `OCRProviderError`, `VisionProviderError`, `ResearchExportError`.

Three most likely failure modes and their handling:

0. **Silent wrong-frame on VFR / long-GOP sources** (the single most-likely failure) →
   extraction is VFR-aware (see `frames.py`): accurate seek is forced when
   `MediaAsset.is_vfr`, the actual decoded timestamp is recorded, and a `vfr_warning`
   surfaces in the manifest. A frame silently off by seconds is worse than a loud error.
1. **A region fails mid-run** (bad seek, corrupt GOP) → record a region-level error in the
   manifest, continue other regions, return a **partial** manifest. Never abort a long
   video for one bad region.
2. **Vision/OCR provider errors or times out** → log, drop the optional annotation, fall
   back to local ranking/selection. AI failure never fails the run.
3. **FFmpeg unavailable / seek past EOF** → surface an actionable message
   (`FFmpegUnavailableError` with the config'd path; `FrameExtractionError` with the
   requested vs. clamped timestamp), preserving stderr for debug logging. Never log secrets.

All FFmpeg calls keep the existing `timeout=` discipline and `TimeoutExpired` cleanup of
partial outputs (matches the repo's ffmpeg-hygiene rule).

## Success Criteria

Carried from the brain dump; the run is correct when:

- A frame can be extracted at an exact timestamp (`forgeframe frame … --timestamp`).
- A burst can be extracted across a region, respecting `max_frames` (auto-widened interval).
- Scenes can be detected within a range, with min-gap and uniform-sampling fallback.
- A transcript can be loaded (JSON/SRT/VTT) and queried by keyword and by time range.
- Given a transcript + query, `research_video()` yields a compact, deduplicated candidate
  set and selects a deterministic default with **no AI configured**.
- A completed run writes `research/{index.md, manifest.json, screenshots/NNN-slug.ext}`,
  and optional Obsidian output.
- Every command supports `--json` for agent consumption.
- Existing 2,189 tests still pass; existing CLI commands unchanged; no second FFmpeg
  execution path introduced; manifest validates against its versioned schema.

## Exclusions (non-goals)

Not a nonlinear editor; does not replace Kdenlive; not a general DAM; no required graph DB,
vector DB, or cloud AI; never uploads whole videos to a provider (frames only, and only
when explicitly enabled); does not decide project research goals; no new frontend; no
stylistic rewrite of stable modules. OpenCV is explicitly excluded (Fork 3).

## Open Questions

1. **Sharpness backend availability** — numpy+Pillow are new optional deps. Confirm they
   may be added to an optional extra (e.g. `pip install workshop-video-brain[research]`)
   vs. required. *Changes:* whether FFmpeg-only scoring is a permanent fallback or a
   stopgap.
2. **`MediaAsset.source_id` identity** — current hash is MD5 of first 64KB. Adequate as a
   cache key for frame extraction? *Changes:* the cache-key contract in phase 5; may need a
   size+mtime composite (the spec's suggested media_probe key already lists these).
3. **Region → concept mapping for multi-topic queries** — when a query names 5 concepts,
   is selection "best-per-region" or "best-per-concept" (a concept may span regions)?
   *Changes:* the select stage and how `max_results` is apportioned.
4. **Transcript-free scene research default** — should `research` with no transcript and no
   query default to whole-video scene sampling, or require an explicit `--range`? *Changes:*
   guardrails against extracting hundreds of candidates from a long video.

## Extension-Point Contracts (phases 4–5, intentionally interface-only)

- **`OcrProvider.extract_text(image_path) -> str`** — local (tesseract) default; cloud
  providers pluggable; never on core path; keyed cache on image hash + provider + config.
- **`VisionFrameEvaluator.rank_candidates(region, candidates, query?) -> list[FrameEvaluation]`**
  — optional; API keys never enter the manifest; local deterministic fallback required;
  keyed cache on candidate image hashes + query + transcript excerpt + provider + model +
  prompt version.
- **External-agent handshake** — `generate_frame_candidates` returns a candidate manifest;
  a follow-up `select_candidate(candidate_ids)` accepts the agent's choice and proceeds to
  export. Agents never construct FFmpeg commands. **State persistence:** the two calls are
  separate CLI/tool invocations, so `generate_frame_candidates` writes candidate images to
  `candidates/` and a `candidates.json` (stable candidate IDs) to disk; `select_candidate`
  rehydrates from `candidates.json`. Nothing is held only in memory between calls.
- **Caching** — optional, off by default, `--no-cache`/`--force` supported, inspectable,
  never reuses results when the source file changed. Cache-key inputs per stage as listed
  in the brain dump (media_probe, scene_detection, frame_extraction, ocr, vision).
- **Future MCP tools** — `probe_video`, `search_transcript`, `get_transcript_context`,
  `extract_frame`, `extract_frame_burst`, `detect_scenes`, `generate_frame_candidates`,
  `select_candidate`, `export_research_package` — thin wrappers over the same stage
  functions the CLI uses.

## Approaches Considered

- **Approach A — Literal spec structure** (new top-level `forgeframe/{core,transcript,
  visual_research}` package). *Pro:* matches the spec's diagram exactly. *Con:* forks the
  established `edit_mcp` convention, risks a parallel FFmpeg/config/model stack — the exact
  thing the spec forbids. **Rejected.**
- **Approach B — Extend `edit_mcp` (adapters + pipelines + core/models).** *Pro:* one
  convention, one FFmpeg path, one config, reuses `MediaAsset`/`TranscriptSegment`/whisper/
  Obsidian writer; lowest backward-compat risk. *Con:* slightly less tidy than a dedicated
  package namespace. **Selected.**
- **Approach C — Standalone research daemon/service** (separate process, REST/local
  daemon). *Pro:* clean isolation, future UI-friendly. *Con:* massive over-engineering for a
  local-first CLI; contradicts "preserve usefulness as a standalone CLI"; premature. Kept
  as a documented *future* extension point only. **Rejected for now.**

## Commander's Intent

**Desired End State:** Running `forgeframe research <video> --transcript <t> --query <q>`
(and its `--json` form) with **no AI configured** produces a `research/` package —
`index.md`, `manifest.json`, and zero-padded, slugged screenshots — where each capture is
a sharp, deduplicated, correctly-timestamped frame relevant to the query, and the manifest
validates against its versioned schema. Individual stages (`frame`, `scenes`,
`transcript`) are independently runnable. The existing 2,189 tests still pass and no
existing CLI command changes behavior.

**Purpose:** Turn ForgeFrame into a media-analysis *backend* so a human, CLI, or AI agent
can request visual evidence for a transcript concept or region without inspecting a whole
video or hand-writing FFmpeg. ForgeFrame owns deterministic extraction; agents own
reasoning about relevance.

**Constraints:**
- MUST route all FFmpeg/ffprobe through the single existing execution path (`run_ffmpeg`,
  `probe_media`); no second FFmpeg system.
- MUST keep the deterministic core fully functional with zero AI/OCR/vision configured.
- MUST NOT overwrite source media, and MUST NOT overwrite an existing `research/` output
  dir without an explicit flag.
- MUST force accurate seek on VFR sources and record the actual extracted timestamp.
- MUST cap candidate generation: transcript-free whole-video research REQUIRES an explicit
  `--range` or falls back to bounded uniform sampling with a hard candidate ceiling — never
  unbounded extraction on a long video.
- MUST keep API keys out of manifests and logs; never upload whole videos to any provider.
- MUST preserve backward compatibility of `TranscriptSegment` and `Config` (additive only).

**Freedoms:**
- The agent MAY choose internal function/file names within the placement in Fork 1.
- The agent MAY choose pHash vs. dHash as the default dedup hash (both acceptable).
- The agent MAY organize new tests under the existing `tests/unit` + `tests/integration`
  layout as it sees fit.
- The agent MAY pick the exact `manifest_version` string (e.g. `"1.0"`).

**Committed interface/contract defaults:**
- Runner extension → **Default:** `run_ffmpeg(args, input_path, output_path, overwrite=True,
  dry_run=False, pre_input_args: list[str] | None = None)` — `pre_input_args` emitted
  between `ffmpeg -y` and `-i`. _(override only if a cleaner seam emerges)_.
- Extraction entry → **Default:** `extract_frame(video_path, timestamp_seconds,
  output_path=None, quality="high", fmt="png") -> FrameCandidate`. Burst:
  `extract_frame_burst(video_path, start_seconds, end_seconds, interval_seconds=0.5,
  max_frames=20) -> list[FrameCandidate]`.
- Scene entry → **Default:** `detect_scene_changes(video_path, start_seconds=None,
  end_seconds=None, threshold=0.30, minimum_gap_seconds=1.0) -> list[SceneChange]` where
  `SceneChange = {timestamp_seconds: float, score: float}`.
- Service entry → **Default:** `research_video(source, transcript=None, query=None,
  topics=None, timestamp_ranges=None, config: ResearchConfig | None = None) ->
  ResearchManifest`.
- Provider interfaces → **Agent-free:** any consistent shape matching the `OcrProvider` /
  `VisionFrameEvaluator` contracts in Extension-Point Contracts is acceptable.
- Config → **Default:** `ResearchConfig` Pydantic model with the nested groups named in
  Fork 2; CLI flags override fields of the same name.

## Execution Guidance

**Observe:**
- `uv run pytest tests/ -v` result after each component (regression signal for the 2,189).
- ffprobe/ffmpeg stderr on every extraction; non-zero `FFmpegResult.success`.
- Candidate counts logged before/after filtering and dedup (spec logging requirement).

**Orient:**
- Follow the `edit_mcp` three-layer convention: models in `core/models`, tool wrappers in
  `edit_mcp/adapters`, orchestration in `edit_mcp/pipelines`. Mirror an existing feature
  (e.g. `pipelines/pacing_analyzer.py`, `pipelines/clip_search.py`) for structure.
- New models extend `core/models/_base.py::SerializableMixin`.
- Match the ffmpeg-hygiene rules in `CLAUDE.md` (always pass `timeout=`, catch
  `TimeoutExpired`, clean partial outputs; `-vn` rule is audio-only, N/A here).

**Escalate When:**
- Adding a new runtime dependency (numpy, Pillow, pytesseract) → recommend + human approve.
- Changing `run_ffmpeg`'s signature beyond the additive `pre_input_args` default.
- Any change to `MediaAsset` or `TranscriptSegment` beyond additive optional fields.
- The manifest schema shape (versioned public contract) — agent drafts, human confirms v1.

**Shortcuts (apply without deliberation):**
- Use `run_ffmpeg` for all encode/extract; use `probe_media` for all metadata.
- Reuse `MediaAsset` as the source model — do not create a `MediaSource`.
- Reuse `whisper_engine` for generation; the repository only *reads* transcripts.
- Reuse `production_brain/notes/writer.py` for Obsidian output (validate its API first).
- Tests: `tests/unit/test_*.py` and `tests/integration/test_*_smoke.py`, real fixtures in
  `tests/fixtures/media_generated/` (`music_cinematic_short.mp3`,
  `test_audio_with_silence.mp4`, `greenscreen_reporter_720.mp4` for video frames).

## Decision Authority

**Agent Decides Autonomously:** internal naming/file layout within Fork 1; test design;
dedup hash choice; error-message wording; slug/filename algorithm; log levels.

**Agent Recommends, Human Approves:** adding numpy/Pillow/pytesseract to pyproject (optional
extra); `run_ffmpeg` signature change; `manifest_version` and manifest schema v1; any
`MediaAsset`/`TranscriptSegment` field additions; the `research/` overwrite-guard behavior.

**Human Decides:** whether OpenCV is ever allowed (currently excluded); whether cloud
vision/OCR providers ship; the optional-dependency-extra name and packaging story.

## War-Game Results

**Most Likely Failure:** silent wrong-frame extraction on VFR / long-GOP footage →
mitigated by VFR-aware accurate seek + recorded actual timestamp + manifest `vfr_warning`
(Error Handling mode 0).

**Scale Stress:** 2-hour video, transcript-free, whole-video sampling → candidate/disk
explosion → mitigated by the constraint requiring `--range`/transcript and a hard
`max_raw_candidates` ceiling with `keep_candidates=false` cleanup.

**Dependency Risk:** numpy/Pillow/tesseract absent → scoring/OCR degrade gracefully behind
their interfaces (FFmpeg-only metrics, OCR skipped), logged; FFmpeg absent → loud
`FFmpegUnavailableError` at first use (acceptable, matches existing `Config` checks).

**Maintenance Assessment (6-month):** strong — the design rides the established `edit_mcp`
convention, reuses named existing modules, and documents every fork's rationale. A new
contributor mirrors an existing pipeline. Risk concentrated in the manifest schema, which
is versioned to allow evolution.

## Evaluation Metadata
- Evaluated: 2026-07-14
- Cynefin Domain: Complicated
- Critical Gaps Found: 1 (1 resolved)
- Important Gaps Found: 3 (3 resolved)
- Suggestions: 1 (tracked as Open Question #2)

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-07-14-forgeframe-visual-research-media-intelligence-design.md`)
- [ ] Resolve the four Open Questions during speccing (esp. optional-dep strategy and cache-key identity)
- [ ] Sequence build as: phase 1 primitives → phase 2 pipeline → phase 3 export/Obsidian → phase 4 provider contracts → phase 5 caching/perf
- [ ] Add `research`-tagged optional dependency extra (numpy, Pillow, pytesseract) to pyproject
