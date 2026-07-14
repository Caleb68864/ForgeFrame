# ForgeFrame Visual Research & Media Intelligence

## Meta
- Client: —
- Project: ForgeFrame / Workshop Video Brain
- Repo: ForgeFrame (`workshop-video-brain/`)
- Date: 2026-07-14
- Author: Caleb Bennett
- Source design: `docs/plans/2026-07-14-forgeframe-visual-research-media-intelligence-design.md` (status: evaluated)
- Quality scores (/35): Outcome 5, Scope 5, Decision guidance 5, Edge coverage 4, Acceptance criteria 4, Decomposition 4, Purpose alignment 5 = **32/35**

## Outcome
ForgeFrame gains a deterministic, local-first visual-research capability. Given a video,
an existing transcript, and optionally a query / topic list / timestamp range, the system
produces a `research/` package (`index.md`, `manifest.json`, zero-padded slugged
screenshots) where each capture is a sharp, deduplicated, correctly-timestamped frame
relevant to the request — with **no AI configured**. Individual primitives (frame, scenes,
transcript) are independently runnable via CLI and Python API. The existing 2,189 tests
still pass and no existing CLI command changes behavior.

## Intent
**Trade-off hierarchy (highest first):**
1. Reuse existing primitives over new parallel implementations — one FFmpeg execution path
   (`run_ffmpeg`), one probe→model path (`probe_media`→`MediaAsset`), one config system.
2. Correctness of extracted frames over speed — accurate seek, VFR-aware, record the real
   extracted timestamp.
3. Deterministic core over AI — every stage works with zero AI/OCR/vision configured.
4. Minimal, Windows-friendly dependencies over convenience — numpy+Pillow (optional
   extra), never OpenCV.

**Decision boundaries — stop and ask when:** adding a runtime dependency; changing
`run_ffmpeg`'s signature beyond the additive `pre_input_args`; any non-additive change to
`MediaAsset` or `TranscriptSegment`; finalizing the public `manifest_version` schema.
Otherwise decide autonomously (internal naming, file layout, test design, pHash vs dHash).

## Context
ForgeFrame already owns the reusable primitives this feature builds on:
- **FFmpeg execution:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/runner.py::run_ffmpeg` (structured `FFmpegResult`, 600s timeout). It currently emits `ffmpeg -y -i <input> <args> <output>` — input before args — so it cannot place `-ss` before `-i` for fast seek without an additive change.
- **Media probe:** `.../adapters/ffmpeg/probe.py::probe_media` → `MediaAsset` (duration_seconds, fps, width, height, codecs, `is_vfr`, 64KB MD5 hash). This is the spec's `MediaSource`; reuse it.
- **Transcript model:** `core/models/transcript.py::TranscriptSegment` (start/end_seconds, text, words, confidence). Extended additively here.
- **Transcript generation:** `.../adapters/stt/whisper_engine.py` (faster-whisper). Unchanged; consumed only.
- **Obsidian writing:** `.../production_brain/notes/writer.py` (section-safe, frontmatter-merge). Reused by export.
- **Surfaces:** Click CLI `app/cli.py` (`main` group, lazy imports inside commands); FastMCP tools `edit_mcp/server/tools.py`.
- **Conventions:** models in `core/models`, external-tool wrappers in `edit_mcp/adapters`, orchestration in `edit_mcp/pipelines`, all models extend `core/models/_base.py::SerializableMixin`. FFmpeg hygiene: always pass `timeout=`, catch `TimeoutExpired`, clean partial outputs (`CLAUDE.md`).
- Absent today (this spec builds them): transcript repository/parsers, frame extraction, scene detection, candidate generation, local scoring, perceptual dedup, manifest/export.

## Requirements
1. A frame can be extracted at an exact timestamp via Python API and `forgeframe frame … --timestamp`.
2. A burst can be extracted across a region, respecting `max_frames` (auto-widened interval, chronological, no duplicate timestamps).
3. Scene changes can be detected within a range via FFmpeg, with configurable threshold, minimum gap, and uniform-sampling fallback when none are found.
4. A transcript (JSON/SRT/VTT) can be loaded, normalized to `TranscriptSegment[]`, searched by keyword, and sliced by time range / ±N-second context.
5. `research_video()` produces `ResearchRegion[]` → `FrameCandidate[]` → deduplicated `ResearchCapture[]` and selects a deterministic default per region with no AI configured.
6. A completed run writes `research/{index.md, manifest.json, screenshots/NNN-slug.ext}`; `manifest.json` validates against a versioned schema and never contains secrets.
7. Every new CLI command supports `--json` machine output.
8. Extraction is VFR-aware: accurate seek is forced when `MediaAsset.is_vfr`, and the actual extracted timestamp plus any `vfr_warning` are recorded.
9. All FFmpeg/ffprobe goes through the existing `run_ffmpeg`/`probe_media`; no second execution path is introduced.
10. The deterministic core imports no AI/OCR/vision library; scoring degrades gracefully when numpy/Pillow are absent.
11. Existing 2,189 tests pass; existing CLI commands unchanged.

## Sub-Specs

---
sub_spec_id: SS-01
phase: run
depends_on: []
---

### 1. Domain models, ResearchConfig, and transcript extension
- **Scope:** Add the `visual_research` domain models and config; extend `TranscriptSegment` additively; add tesseract-availability + ffmpeg-version helpers to the config module. No behavior wired yet.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/core/models/visual_research.py`
  - `tests/unit/test_visual_research_models.py`
- **Files (modify):**
  - `workshop-video-brain/src/workshop_video_brain/core/models/transcript.py`
  - `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py`
  - `workshop-video-brain/src/workshop_video_brain/app/config.py`
- **Decisions:** `ResearchConfig` is a `SerializableMixin` Pydantic model with nested groups `windowing`, `candidate_generation`, `scene_detection`, `quality`, `deduplication`, `ocr`, `vision`, `export`, each with the defaults from the design. `SceneChange` = `{timestamp_seconds: float, score: float}`. `FrameVisualMetrics` carries all optional metric fields. Precedence (documented, enforced by callers): explicit args/CLI > `WVB_*` env > `ResearchConfig` defaults.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `visual_research.py` defines `ResearchQuery`, `ResearchRegion`, `FrameVisualMetrics`, `FrameCandidate`, `ResearchCapture`, `ResearchManifest`, `FrameEvaluation`, `SceneChange`, and `ResearchConfig`, all extending `SerializableMixin`.
  - `[STRUCTURAL]` `FrameCandidate` has fields `candidate_id, source_id, region_id (optional), timestamp_seconds, image_path, width, height, extraction_method, metrics: FrameVisualMetrics, metadata`; `extraction_method` is constrained to `{exact_timestamp, uniform_burst, scene_change, adaptive, manual}`.
  - `[STRUCTURAL]` `TranscriptSegment` gains optional `segment_id`, `speaker`, `tags: list[str] = []`, `metadata: dict = {}`; existing fields and their defaults are unchanged (additive only). `metadata` is handled when present AND when absent.
  - `[STRUCTURAL]` `core/models/__init__.py` imports and re-exports every new public model in `__all__`.
  - `[STRUCTURAL]` `app/config.py::Config` gains `tesseract_available: bool` (via `shutil.which`) and the loader populates it without raising when tesseract is absent.
  - `[MECHANICAL]` `uv run python -c "from workshop_video_brain.core.models import ResearchManifest, FrameCandidate, ResearchConfig, SceneChange; ResearchConfig()"` exits 0.
  - `[BEHAVIORAL]` A `ResearchManifest` containing a nested `MediaAsset`, one `ResearchRegion`, and one `ResearchCapture` round-trips through the `SerializableMixin` serialize→deserialize path unchanged.
  - `[MECHANICAL]` `uv run pytest tests/unit/test_visual_research_models.py -q` passes.

---
sub_spec_id: SS-02
phase: run
depends_on: ['SS-01']
---

### 2. FFmpeg runner pre-input seek + frame extraction adapter
- **Scope:** Add an additive `pre_input_args` parameter to `run_ffmpeg`, then build the frame-extraction adapter on top of it (exact, burst, centered). VFR-aware accurate seek.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/frames.py`
  - `tests/integration/test_frame_extraction_smoke.py`
- **Files (modify):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/runner.py`
- **Decisions:** `run_ffmpeg(args, input_path, output_path, overwrite=True, dry_run=False, pre_input_args: list[str] | None = None)` — `pre_input_args` emitted between `ffmpeg -y` and `-i` (default `None` → `[]`, byte-identical to today). `extract_frame(video_path, timestamp_seconds, output_path=None, quality="high", fmt="png") -> FrameCandidate`; `quality="high"` uses accurate seek (`-ss` after `-i`), `quality="fast"` uses `pre_input_args=["-ss", str(t)]`. On `MediaAsset.is_vfr` (probe first), force accurate seek and set `metrics.metadata`/candidate `vfr_warning`. All FFmpeg calls pass `timeout=` and catch `subprocess.TimeoutExpired`, cleaning any partial output (repo FFmpeg-hygiene rule in `CLAUDE.md`). `extract_frame_burst(video_path, start_seconds, end_seconds, interval_seconds=0.5, max_frames=20) -> list[FrameCandidate]` widens interval when the count would exceed `max_frames`, dedupes timestamps, returns chronological. `extract_centered_burst(video_path, anchor_seconds, before_seconds=3, after_seconds=5, interval_seconds=0.5) -> list[FrameCandidate]`.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `runner.py::run_ffmpeg` signature includes `pre_input_args: list[str] | None = None`; when `None`/omitted the emitted command is unchanged (`ffmpeg -y -i <input> <args> <output>`).
  - `[BEHAVIORAL]` Calling `run_ffmpeg` with `pre_input_args=["-ss", "1.0"]` places `-ss 1.0` before `-i` in `FFmpegResult.command`.
  - `[STRUCTURAL]` `frames.py` exposes `extract_frame`, `extract_frame_burst`, `extract_centered_burst` with the signatures above, each returning `FrameCandidate`(s).
  - `[BEHAVIORAL]` `extract_frame_burst` over a 2s range with `interval_seconds=0.1, max_frames=5` returns exactly 5 chronological candidates with no duplicate `timestamp_seconds`.
  - `[BEHAVIORAL]` `extract_frame` on `tests/fixtures/media_generated/greenscreen_reporter_720.mp4` at `timestamp_seconds=0.5` writes a non-empty PNG whose probed dimensions match the candidate's `width`/`height`, and the candidate records the actual extracted timestamp.
  - `[BEHAVIORAL]` When the source probes as VFR, `extract_frame` forces accurate seek and sets a `vfr_warning` on the candidate.
  - `[MECHANICAL]` `uv run pytest tests/integration/test_frame_extraction_smoke.py -q` passes.
  - `[MECHANICAL]` `uv run pytest tests/ -q` shows no regressions in existing runner tests.

---
sub_spec_id: SS-03
phase: run
depends_on: ['SS-01']
---

### 3. FFmpeg scene-change detection adapter
- **Scope:** Detect scene changes via FFmpeg within an optional time range; return `SceneChange[]` with min-gap enforcement and a uniform-sampling fallback.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/scene.py`
  - `tests/integration/test_scene_detection_smoke.py`
- **Decisions:** `detect_scene_changes(video_path, start_seconds=None, end_seconds=None, threshold=0.30, minimum_gap_seconds=1.0) -> list[SceneChange]`. Implementation runs FFmpeg `select='gt(scene,threshold)',showinfo` (null muxer) and parses `pts_time` from stderr; enforces `minimum_gap_seconds`; if zero scenes are found, falls back to uniform temporal sampling across the range at a bounded count. Uses `run_ffmpeg` (or a probe-style subprocess through the shared adapter), never a bespoke exec path, and passes `timeout=` with `TimeoutExpired` handling per the repo FFmpeg-hygiene rule.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `scene.py` exposes `detect_scene_changes` with the signature above, returning `list[SceneChange]`.
  - `[BEHAVIORAL]` On a fixture with known cuts, detected timestamps fall within the range and are spaced by at least `minimum_gap_seconds`.
  - `[BEHAVIORAL]` On a static-source range with no scene change, the function returns a bounded, non-empty uniform sample rather than an empty list.
  - `[MECHANICAL]` `uv run pytest tests/integration/test_scene_detection_smoke.py -q` passes.

---
sub_spec_id: SS-04
phase: run
depends_on: ['SS-01']
---

### 4. Transcript parsers + repository
- **Scope:** Parse SRT/VTT/JSON (and the existing ForgeFrame `Transcript`) into `TranscriptSegment[]`, and provide query/slice/search over them.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/transcript/__init__.py`
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/transcript/parsers.py`
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/transcript_repository.py`
  - `tests/unit/test_transcript_repository.py`
  - `tests/fixtures/transcripts/sample.srt`
  - `tests/fixtures/transcripts/sample.vtt`
  - `tests/fixtures/transcripts/sample.json`
- **Decisions:** `parse_transcript(path) -> list[TranscriptSegment]` auto-detects format by extension + sniffing. `TranscriptRepository` wraps the segments with: `search(term, case_insensitive=True) -> list[TranscriptSegment]`, `overlapping(start, end) -> list[TranscriptSegment]`, `context_around(timestamp, seconds) -> list[TranscriptSegment]`, `merge_adjacent(gap_seconds) -> list[TranscriptSegment]`. Generation stays in `whisper_engine` — the repository only reads. The `sample.json` fixture MUST contain at least one segment whose text matches the SS-10/SS-11 integration query ("reporter on camera") with `start_seconds`/`end_seconds` inside the `greenscreen_reporter_720.mp4` duration, so the end-to-end tests resolve a non-empty region.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `parsers.py` exposes `parse_transcript(path)` returning `list[TranscriptSegment]`; `transcript_repository.py` defines `TranscriptRepository` with the four query methods above.
  - `[BEHAVIORAL]` Parsing `sample.srt`, `sample.vtt`, and `sample.json` each yields segments with correct `start_seconds`/`end_seconds`/`text` (spot-checked against fixture content).
  - `[BEHAVIORAL]` `overlapping(a, b)` returns exactly the segments intersecting `[a, b]`; `context_around(t, n)` returns segments within `±n` seconds of `t`.
  - `[BEHAVIORAL]` `search` is case-insensitive by default and matches substrings.
  - `[MECHANICAL]` `uv run pytest tests/unit/test_transcript_repository.py -q` passes.

---
sub_spec_id: SS-05
phase: run
depends_on: ['SS-01', 'SS-04']
---

### 5. Research region selector
- **Scope:** Turn keyword matches / explicit segment IDs / timestamp lists / ranges into bounded `ResearchRegion[]` with pre/post-roll expansion, max-region clamp, and near-adjacent merging.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/__init__.py`
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/regions.py`
  - `tests/unit/test_research_regions.py`
- **Decisions:** `select_regions(repo: TranscriptRepository | None, query: ResearchQuery, config: ResearchConfig) -> list[ResearchRegion]`. Windowing defaults: pre-roll 3.0, post-roll 5.0, max region 30.0, merge gap 2.0. Each region records `source_method`, `reason`, `transcript_segment_ids`, `transcript_excerpt`, `anchor_seconds`. AI region suggestions (future) pass through the same windowing — never trusted as final.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `regions.py` exposes `select_regions(...)` returning `list[ResearchRegion]`; the `visual_research` package `__init__.py` exists.
  - `[BEHAVIORAL]` A keyword hit at `t` produces a region `[t-pre_roll, end+post_roll]` clamped to `maximum_region_seconds`, with `source_method="query"` (or `"transcript"`) and a populated `reason`.
  - `[BEHAVIORAL]` Two matches within `merge_gap_seconds` collapse into one region whose `transcript_segment_ids` union both.
  - `[BEHAVIORAL]` An explicit timestamp list with no transcript yields `manual_timestamp` regions windowed around each timestamp.
  - `[MECHANICAL]` `uv run pytest tests/unit/test_research_regions.py -q` passes.

---
sub_spec_id: SS-06
phase: run
depends_on: ['SS-02', 'SS-03', 'SS-05']
---

### 6. Adaptive candidate generation
- **Scope:** For each region, produce a capped `FrameCandidate[]` combining an anchor frame, a uniform burst, and scene-change frames.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/candidates.py`
  - `tests/integration/test_candidate_generation_smoke.py`
- **Decisions:** `generate_candidates(video_path, region: ResearchRegion, source: MediaAsset, config: ResearchConfig) -> list[FrameCandidate]`. Steps: anchor near `region.anchor_seconds` if present; uniform burst via `extract_frame_burst`; scene-change frames via `detect_scene_changes` + `extract_frame`; merge, dedupe identical timestamps, cap at `max_raw_candidates` (default 30). Static-source fallback: periodic extraction when no scene changes.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `candidates.py` exposes `generate_candidates(...)` returning `list[FrameCandidate]` tagged with the correct `extraction_method` per source.
  - `[BEHAVIORAL]` For a region on a real fixture, the returned count is ≤ `max_raw_candidates` and includes at least one `uniform_burst` candidate; when scene changes exist, at least one `scene_change` candidate.
  - `[BEHAVIORAL]` On a static region (no scene changes), candidates are still produced via periodic fallback.
  - `[MECHANICAL]` `uv run pytest tests/integration/test_candidate_generation_smoke.py -q` passes.

---
sub_spec_id: SS-07
phase: run
depends_on: ['SS-01']
---

### 7. Local frame quality scoring
- **Scope:** Compute independently-inspectable local metrics behind a `FrameScorer` interface, with FFmpeg-cheap metrics always and numpy/Pillow metrics when available.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/scoring.py`
  - `tests/unit/test_frame_scoring.py`
- **Decisions:** `class FrameScorer` with `score(candidate: FrameCandidate, config: ResearchConfig) -> FrameVisualMetrics`. Brightness/black/overexposure via FFmpeg `signalstats`/`blackdetect` (no image lib). Sharpness (variance-of-Laplacian), entropy, text-density via numpy+Pillow, gated behind a capability check — if numpy/Pillow are absent, those fields stay `None` and a debug log is emitted; core scoring still returns. Metrics stay separate on `FrameVisualMetrics` — never collapsed into one opaque number. Configurable weights + per-mode profiles (`software_ui`, `slide_deck`, `physical_demo`) drive a derived rank used by callers, not stored as the only signal.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `scoring.py` defines `FrameScorer` with `score(...) -> FrameVisualMetrics` and a `rank(candidates, config)` helper honoring configurable weights + mode profiles.
  - `[BEHAVIORAL]` A near-black test image scores low brightness and is rejected by the quality gate; a sharp UI-like image scores higher sharpness than a Gaussian-blurred copy.
  - `[STRUCTURAL]` numpy/Pillow imports are lazy/guarded; with them absent, `score` returns `FrameVisualMetrics` with pixel-metric fields `None` and does not raise. Absence is handled AND presence is handled.
  - `[MECHANICAL]` `uv run pytest tests/unit/test_frame_scoring.py -q` passes.

---
sub_spec_id: SS-08
phase: run
depends_on: ['SS-01']
---

### 8. Perceptual deduplication
- **Scope:** Remove visually redundant candidates within a region (optionally across final captures), preserving the highest-ranked of each cluster.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/dedup.py`
  - `tests/unit/test_deduplication.py`
- **Decisions:** `deduplicate(candidates: list[FrameCandidate], threshold: int, rank_key) -> tuple[list[FrameCandidate], dict]` returns kept candidates plus a debug map of duplicate relationships. Default perceptual hash is pHash on numpy arrays (agent MAY choose dHash); Hamming distance ≤ `threshold` (default 8) = duplicate. Never deletes source candidate images; only filters the list. Records `perceptual_hash` on each candidate's metrics.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `dedup.py` exposes `deduplicate(...)` returning kept candidates + a duplicate-relationship map; each candidate gets a `perceptual_hash`.
  - `[BEHAVIORAL]` Two near-identical frames collapse to one (the higher-ranked kept); two visually distinct frames both survive.
  - `[BEHAVIORAL]` Dedup filters the list but does not delete any candidate image file from disk.
  - `[MECHANICAL]` `uv run pytest tests/unit/test_deduplication.py -q` passes.

---
sub_spec_id: SS-09
phase: run
depends_on: ['SS-01']
---

### 9. Manifest + research package export
- **Scope:** Write the research package: copy selected frames to `screenshots/`, generate filenames, write `manifest.json` (versioned, secret-free) and `index.md`, and support Obsidian output via the existing notes writer.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/export.py`
  - `tests/unit/test_research_export.py`
- **Decisions:** `export_package(manifest: ResearchManifest, output_dir, obsidian=False, keep_candidates=False) -> ResearchManifest`. Filenames: `NNN-slug.ext` (zero-padded, filesystem-safe slug, path-traversal-safe, duplicate-title-safe). `manifest_version="1.0"`. Manifest uses relative paths for package assets + separate absolute source path; `processing.configuration` is the sanitized `ResearchConfig`; no API keys ever written. Obsidian mode reuses `production_brain/notes/writer.py` (validate its API first) with relative image embeds and configurable destination — no parallel Obsidian implementation. Guards against overwriting an existing `output_dir` without an explicit flag.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `export.py` exposes `export_package(...)`; slug generation rejects path traversal and de-collides duplicate titles.
  - `[BEHAVIORAL]` A run with two captures writes `index.md`, `manifest.json`, and `screenshots/001-*.png` + `002-*.png`; `index.md` embeds relative image paths and includes timestamp, transcript excerpt, and selection reason per capture.
  - `[STRUCTURAL]` `manifest.json` contains `manifest_version`, relative asset paths, a separate absolute source path, and `processing.configuration`; a scan of the file for common secret keys finds none.
  - `[BEHAVIORAL]` Obsidian mode routes through `production_brain/notes/writer.py` (no direct file-writing of notes in `export.py`).
  - `[MECHANICAL]` `uv run pytest tests/unit/test_research_export.py -q` passes.

---
sub_spec_id: SS-10
phase: run
depends_on: ['SS-04', 'SS-06', 'SS-07', 'SS-08', 'SS-09']
---

### 10. Research service orchestrator
- **Scope:** Wire the full pipeline into one entry point with per-region error isolation, stage enable/disable, deterministic default selection, and manifest assembly.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/service.py`
  - `tests/integration/test_research_service_smoke.py`
  - `tests/integration/ss10-integration-evidence.md`
- **Decisions:** `research_video(source, transcript=None, query=None, topics=None, timestamp_ranges=None, config: ResearchConfig | None = None) -> ResearchManifest`. Pipeline: `probe_media` → resolve transcript (load via repository, or transcribe if flagged, or transcript-free) → `select_regions` → `generate_candidates` → score → (OCR optional, skipped by default) → `deduplicate` → (vision optional, skipped by default) → deterministic select (top-ranked per region) → `export_package`. A failing region is recorded in the manifest and skipped; the run returns a partial manifest rather than aborting. Transcript-free + no `--range` uses bounded uniform sampling with the hard candidate ceiling.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `service.py` exposes `research_video(...)` with the signature above, returning `ResearchManifest`.
  - `[INTEGRATION]` End-to-end on a real fixture + supplied transcript + query, with no AI configured, produces a `ResearchManifest` with ≥1 region and ≥1 capture, and writes a valid `research/` package; recorded in `ss10-integration-evidence.md`.
  - `[BEHAVIORAL]` When one region raises during extraction, the manifest records a region-level error and still returns captures for the healthy regions (partial manifest).
  - `[BEHAVIORAL]` Running with no transcript and no range does not exceed the configured candidate ceiling.
  - `[MECHANICAL]` `uv run pytest tests/integration/test_research_service_smoke.py -q` passes.

---
sub_spec_id: SS-11
phase: run
depends_on: ['SS-02', 'SS-03', 'SS-04', 'SS-10']
---

### 11. CLI commands (research / frame / scenes / transcript) with --json
- **Scope:** Add the four Click command groups to the existing `main` group, each with a `--json` machine-output mode, wiring to the stage functions and the service. This is the entry-point integration sub-spec.
- **Files (new):**
  - `tests/integration/test_cli_research_smoke.py`
  - `tests/integration/ss11-integration-evidence.md`
- **Files (modify):**
  - `workshop-video-brain/src/workshop_video_brain/app/cli.py`
- **Decisions:** Follow the existing `@main.group()` + lazy-import-inside-command pattern. `forgeframe`/`wvb research <video> [--transcript --query --topic… --timestamp… --range… --output ./research --max-results 20 --pre-roll --post-roll --scene-detection/--no-scene-detection --ocr --vision --keep-candidates --obsidian --dry-run --json]`; `frame <video> --timestamp [--burst A:B --interval --format --json]`; `scenes <video> [--range --threshold --json]`; `transcript search/context/export [--json]`. `--dry-run` prints resolved regions + expected candidate counts + output paths without extracting. `--json` emits the machine-readable result shape from the design.
- **Acceptance criteria:**
  - `[STRUCTURAL]` `app/cli.py` registers `research`, `frame`, `scenes`, and `transcript` under the existing `main` group; no existing command is renamed or removed.
  - `[INTEGRATION]` `wvb research <fixture> --transcript <fixture> --query "…" --output <tmp> --json` runs end-to-end with no AI and prints valid JSON containing `source`, `regions`, and `captures`, and the package exists on disk; recorded in `ss11-integration-evidence.md`.
  - `[BEHAVIORAL]` `wvb frame <fixture> --timestamp 0.5 --json` prints a single capture JSON and writes one image.
  - `[BEHAVIORAL]` `wvb scenes <fixture> --json` prints a JSON list of `{timestamp_seconds, score}`.
  - `[BEHAVIORAL]` `wvb research … --dry-run` prints resolved regions and expected counts and writes no images.
  - `[MECHANICAL]` `uv run pytest tests/integration/test_cli_research_smoke.py -q` passes.
  - `[MECHANICAL]` `uv run pytest tests/ -q` — full suite passes (no regression to the existing 2,189).

---
sub_spec_id: SS-12
phase: run
depends_on: ['SS-07']
---

### 12. Optional research dependency extra
- **Scope:** Declare an optional dependency extra so scoring/dedup/OCR libs install on request without becoming core requirements.
- **Files (modify):**
  - `pyproject.toml`
- **Decisions:** Add `[project.optional-dependencies]` group `research = ["numpy>=1.26", "Pillow>=10.0", "pytesseract>=0.3"]`. Core `dependencies` are unchanged — numpy/Pillow/pytesseract stay optional and lazily imported by SS-07/SS-08. (tesseract binary remains a documented external prerequisite for OCR.)
- **Acceptance criteria:**
  - `[STRUCTURAL]` `pyproject.toml` declares `[project.optional-dependencies].research` with numpy, Pillow, pytesseract; the core `dependencies` array is unchanged.
  - `[MECHANICAL]` `uv run python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert 'research' in d['project']['optional-dependencies']"` exits 0.
  - `[MECHANICAL]` `uv sync` succeeds (core install unaffected).

## Edge Cases
- **VFR / long-GOP source** → force accurate seek via `is_vfr`, record actual timestamp + `vfr_warning` (SS-02). A silently-wrong frame is worse than a loud error.
- **Transcript-free long video** → require `--range` or fall back to bounded uniform sampling with a hard candidate ceiling; never unbounded (SS-10).
- **numpy/Pillow absent** → pixel metrics `None`, FFmpeg metrics still computed, logged; core still runs (SS-07).
- **tesseract absent** → OCR disabled (it is off by default); availability recorded in `Config` (SS-01).
- **Region fails mid-run** → region-level error in manifest, partial manifest returned (SS-10).
- **`"handles"/"processes"/"validates"` in behavior** → interpreted **strict** for input validation (reject with specific error) unless a config toggle says otherwise; extraction is **permissive** about seek targets (clamp to `[0, duration]`, record actual).
- **Duplicate capture titles** → de-collided by the slug/numbering algorithm (SS-09).
- **Existing `research/` output dir** → not overwritten without an explicit flag (SS-09).

## Out of Scope
- Vision-model provider implementations, OCR provider implementations beyond the interface + availability check, and the external-agent `generate_candidates`/`select_candidate` two-call handshake implementation (interface contracts documented in the design; deferred to a later spec — phase 4).
- Caching / resumability (phase 5).
- New MCP tool registrations in `edit_mcp/server/tools.py` (thin wrappers over these stage functions; a later spec).
- OpenCV (permanently excluded).
- Any nonlinear-editor, Kdenlive-replacement, DAM, graph-DB, vector-DB, or cloud-AI functionality.
- Non-additive changes to `MediaAsset` or `TranscriptSegment`.

## Constraints
**Musts:**
- Route all FFmpeg/ffprobe through `run_ffmpeg`/`probe_media` (Req 9).
- Deterministic core runs with zero AI/OCR/vision configured (Req 10).
- Force accurate seek on VFR sources; record actual timestamp (Req 8).
- Every new CLI command supports `--json` (Req 7).
- `manifest.json` validates against a versioned schema and contains no secrets (Req 6).

**Must-Nots:**
- No second FFmpeg execution path.
- No overwrite of source media or of an existing `research/` output dir without an explicit flag.
- No API keys in manifests or logs; never upload whole videos to any provider.
- No non-additive change to `MediaAsset`/`TranscriptSegment`/`Config`.
- No OpenCV dependency.

**Preferences:**
- Prefer FFmpeg/ffprobe-native metrics before reaching for numpy/Pillow.
- Prefer mirroring an existing `edit_mcp/pipelines` module for structure.
- Prefer pHash for dedup (dHash acceptable).

**Escalation Triggers:**
- Changing `run_ffmpeg`'s signature beyond the additive `pre_input_args`.
- Finalizing the public `manifest_version` schema shape.
- Any need to add a runtime dependency outside the `research` optional extra.

## Verification
1. `uv run pytest tests/ -q` — full suite green, including all new unit + integration tests, no regression to the existing 2,189.
2. End-to-end: `wvb research tests/fixtures/media_generated/greenscreen_reporter_720.mp4 --transcript tests/fixtures/transcripts/sample.json --query "reporter on camera" --output ./_research_demo --json` — with no AI configured — prints JSON with `source`/`regions`/`captures` and produces `./_research_demo/{index.md, manifest.json, screenshots/001-*.png}`.
3. `wvb frame … --timestamp`, `wvb scenes …`, and `wvb transcript search …` each run standalone and honor `--json`.
4. Spot-check: on a VFR fixture, a capture records a `vfr_warning` and the actual extracted timestamp.

## Phase Specs

Refined by `/forge-prep` on 2026-07-14.

| Sub-Spec | Phase Spec |
|----------|------------|
| SS-01. Domain models, ResearchConfig, transcript extension | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-1-models-config.md` |
| SS-02. FFmpeg runner pre-input seek + frame extraction | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-2-frame-extraction.md` |
| SS-03. Scene-change detection adapter | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-3-scene-detection.md` |
| SS-04. Transcript parsers + repository | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-4-transcript-repository.md` |
| SS-05. Research region selector | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-5-regions.md` |
| SS-06. Adaptive candidate generation | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-6-candidates.md` |
| SS-07. Local frame quality scoring | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-7-frame-scoring.md` |
| SS-08. Perceptual deduplication | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-8-deduplication.md` |
| SS-09. Manifest + research package export | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-9-export.md` |
| SS-10. Research service orchestrator | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-10-service.md` |
| SS-11. CLI commands with --json (integration) | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-11-cli.md` |
| SS-12. Optional research dependency extra | `docs/specs/forgeframe-visual-research-media-intelligence/sub-spec-12-optional-deps.md` |

Index: `docs/specs/forgeframe-visual-research-media-intelligence/index.md`
