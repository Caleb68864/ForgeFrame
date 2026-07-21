# Visual Research MCP Tool Surface + Agent Candidate Handshake

## Meta
- Client: (internal)
- Project: ForgeFrame
- Repo: ForgeFrame (workshop-video-brain plugin)
- Date: 2026-07-21
- Author: Caleb Bennett (coached via Forge)
- Parent spec: `docs/specs/2026-07-14-forgeframe-visual-research-media-intelligence.md` (SS-01..SS-12 complete; this spec is the deferred "MCP tool registrations" + phase-4 agent handshake named in its Out of Scope)
- Quality scores: Outcome 5, Scope 5, Decision guidance 4, Edge coverage 5, Acceptance criteria 5, Decomposition 4, Purpose alignment 5 — **33/35**

## Outcome
Ten `research_*` MCP tools are registered through the existing auto-discovery mechanism and drivable from a Claude session: an agent can probe a video, search its transcript, generate frame candidates for a query, view the candidate images itself, select the best one, and export a research package (screenshots + `manifest.json` + `index.md`) — end to end, with no CLI involvement. The full test suite stays green.

## Intent
**Principle:** the completed visual-research pipeline becomes agent-drivable; Claude itself acts as the vision evaluator via the two-call handshake, removing the need for a vision-provider implementation.

**Trade-off hierarchy:**
1. Correctness of the error contract over breadth of parameters — a tool that fails loudly with a specific error beats one with ten optional knobs.
2. Thin shells over convenience logic — anything beyond validate/call/envelope belongs in `pipelines/visual_research/`.
3. Consistency with the existing 200-tool registry conventions over novel ergonomics.

**Decision boundaries:** decide autonomously on parameter defaults (mirror the underlying stage function defaults verbatim); stop and ask before changing any existing pipeline/adapter signature, adding a runtime dependency, or altering the `candidates.json` schema after SS-03 lands.

## Context
- Parent design doc: `docs/plans/2026-07-14-forgeframe-visual-research-media-intelligence-design.md` — "Extension-Point Contracts" defines the handshake: `generate_frame_candidates` writes candidate images to `candidates/` and a `candidates.json` (stable candidate IDs) to disk; `select_candidate` rehydrates from `candidates.json` and proceeds to export. Agents never construct FFmpeg commands. Nothing is held only in memory between calls.
- Stage functions (all exist, all tested): `research_video`, `select_regions`, `generate_candidates`, `deduplicate`, `FrameScorer`, `export_package` in `edit_mcp/pipelines/visual_research/`; `extract_frame`, `extract_frame_burst` in `edit_mcp/adapters/ffmpeg/frames.py`; `detect_scene_changes` in `edit_mcp/adapters/ffmpeg/scene.py`; `probe_media` in `edit_mcp/adapters/ffmpeg/probe.py`; `parse_transcript` in `edit_mcp/adapters/transcript/parsers.py`; `TranscriptRepository` in `edit_mcp/pipelines/transcript_repository.py`.
- Naming: `research_*` prefix chosen to group the family and avoid collision with the existing `transcript_search` workspace tool. These tools operate on bare media/transcript file paths (per CLAUDE.md, path-first is legitimate for tools not bound to a workspace).
- These tools are **not timeline-affecting**: no project XML is parsed or mutated, so no snapshot step and no melt render proof is required; the integration tier uses real ffmpeg/ffprobe against `tests/fixtures/media_generated/greenscreen_reporter_720.mp4`.

## Requirements
1. Ten tools registered via module auto-discovery with zero shared-file edits: `research_probe_video`, `research_extract_frame`, `research_extract_frame_burst`, `research_detect_scenes`, `research_transcript_search`, `research_transcript_context`, `research_generate_candidates`, `research_select_candidate`, `research_export_package`, `research_run`.
2. Every tool is a thin shell (validate → call stage function → envelope); the only new logic module is `edit_mcp/pipelines/visual_research/handshake.py` (candidates.json persistence, source fingerprint, rehydration, selection).
3. Handshake state is fully disk-persisted: `generate` writes `candidates/*.png` + `candidates.json` with stable IDs (`cand-001`, `cand-002`, … ordered by region then timestamp) and a source fingerprint (absolute path, size bytes, mtime ns); `select`/`export` rehydrate from disk only.
4. Error contract per `server/errors.py`: `@tool_guard` directly under `@mcp.tool()`; only specific constructors (`missing_file`, `not_found`, `invalid_input`, `missing_binary`, `media_unreadable`, `operation_failed`); envelope via `tools_helpers._ok`/`_err`; never a silent fake success.
5. All FFmpeg/ffprobe work routes through the existing adapters (`run_ffmpeg`/`probe_media`) — no second execution path, no hand-rolled argv in shells.
6. Export tools never overwrite an existing non-empty output directory unless `overwrite=True` is passed explicitly.
7. `uv run pytest tests/ -q` green, no regression.

## Sub-Specs

---
sub_spec_id: SS-01
phase: run
depends_on: []
---

### 1. Media read-only tools module
- **Scope:** Four read-only tools wrapping existing ffmpeg adapters, in one grouped domain module. `research_probe_video(video_path)` → `probe_media` result as dict (duration, streams, vfr flag, geometry). `research_extract_frame(video_path, timestamp_seconds, output_path=None, quality="high", fmt="png")` → `extract_frame`, returns the FrameCandidate as dict including actual extracted timestamp. `research_extract_frame_burst(video_path, start_seconds, end_seconds, interval_seconds=0.5, max_frames=20)` → `extract_frame_burst`. `research_detect_scenes(video_path, start_seconds=None, end_seconds=None, threshold=0.30, minimum_gap_seconds=1.0)` → `detect_scene_changes`. Defaults mirror the adapter signatures verbatim.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_media.py`
  - `tests/unit/test_research_media_tools.py`
- **Acceptance criteria:**
  - `[STRUCTURAL]` `research_media.py` defines exactly four `@mcp.tool()` functions, each with `@tool_guard` directly beneath the tool decorator, and imports only the specific error constructors it uses.
  - `[BEHAVIORAL]` `call_tool(research_probe_video, video_path=<greenscreen fixture>)` returns `status="ok"` with `duration_seconds > 0`; a nonexistent path returns the `missing_file` error envelope.
  - `[BEHAVIORAL]` `research_extract_frame` at `t=1.0` on the fixture writes a nonempty PNG and reports the actual timestamp; a timestamp past EOF is clamped (permissive seek per parent spec) and the actual timestamp is recorded in the payload.
  - `[BEHAVIORAL]` `research_detect_scenes` on the fixture returns `status="ok"` with a (possibly empty) list; ffmpeg missing → `missing_binary` envelope (tested via monkeypatched adapter exception).
- **Dependencies:** none

---
sub_spec_id: SS-02
phase: run
depends_on: []
---

### 2. Transcript read-only tools module
- **Scope:** Two tools over the SS-04 (parent spec) parsers/repository. `research_transcript_search(transcript_path, query, limit=10)` → `parse_transcript` + `TranscriptRepository.search`, returns matching segments (id, start/end seconds, text) in transcript order — no relevance score (`TranscriptRepository.search` is unscored; do not invent one). `research_transcript_context(transcript_path, timestamp_seconds, window_seconds=30.0)` → segments overlapping `[t - window, t + window]`, ordered by start time. Accepts `.json`, `.srt`, `.vtt` (whatever `parse_transcript` supports); strict validation — unparseable transcript → `invalid_input` with the parser's cause, never a guess. Test fixtures: use the tracked `tests/fixtures/transcripts/sample.json`, `sample.srt`, and `sample.vtt` (one behavioral case per format).
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_transcript.py`
  - `tests/unit/test_research_transcript_tools.py`
- **Acceptance criteria:**
  - `[BEHAVIORAL]` Searching a fixture transcript for a word present in one segment returns exactly that segment with correct timestamps; a query with zero hits returns `status="ok"` with an empty list (not an error).
  - `[BEHAVIORAL]` `research_transcript_context` at a mid-transcript timestamp returns the overlapping segments in order; a timestamp beyond the transcript returns an empty list with a message noting the transcript's end time.
  - `[BEHAVIORAL]` A malformed transcript file returns the `invalid_input` envelope naming the parse failure; a missing file returns `missing_file`.
- **Dependencies:** none

---
sub_spec_id: SS-03
phase: run
depends_on: []
---

### 3. Handshake pipeline module + generate/select tools
- **Scope:** The two-call agent handshake. New pipeline module `handshake.py` owns all state logic — **Decisions:** it exposes `generate_handshake(video_path, *, transcript_path=None, query=None, start_seconds=None, end_seconds=None, output_dir, max_candidates=None, config=None) -> dict` (runs probe → regions → `generate_candidates` → `FrameScorer` → `deduplicate`, writes `<output_dir>/candidates/*.png` + `<output_dir>/candidates.json`, returns the manifest dict) and `select_from_handshake(candidates_dir, candidate_ids, *, output_dir=None, obsidian=False, keep_candidates=False, overwrite=False) -> dict` (rehydrates `candidates.json`, validates IDs and source fingerprint, **persists the chosen IDs into the `selections` array of `candidates.json` before exporting**, builds `ResearchCapture`s for the chosen candidates, calls `export_package`). `candidate_ids` is a list of one or more IDs; each selected candidate becomes one capture. `handshake.py` also exposes public `load_handshake(candidates_dir) -> dict` (rehydrate + validate schema/fingerprint) — SS-04 consumes it. `candidates.json` schema v1: `{"schema_version": 1, "source": {"path", "size_bytes", "mtime_ns"}, "query", "regions": [...], "candidates": [{"id", "region_id", "timestamp_seconds", "image_path", "extraction_method", "quality_scores"}], "selections": []}`. IDs are `cand-NNN`, zero-padded, ordered by (region index, timestamp). Each candidate entry is the serialized `FrameCandidate` (via its `SerializableMixin` round-trip) plus the `id`/`region_id` keys — the entry shape is the model's shape, so schema and model cannot drift independently. The tools module is a thin shell exposing `research_generate_candidates` and `research_select_candidate` over those two functions.
  <!-- Assumption ASM-5 (resolved by committed default below): region resolution must not require editing service.py -->
  **Decisions (region resolution):** `handshake.py` builds a `ResearchQuery` from its params and calls the **public** `select_regions(repo, query, config)`; when no transcript/query/range is supplied it constructs the bounded uniform-sampling fallback region itself (mirroring `service._fallback_region`, ~15 lines). In-package imports of `service` privates are permitted; **edits** to `service.py` are not.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/handshake.py`
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_candidates.py`
  - `tests/unit/test_research_handshake.py`
  - `tests/unit/test_research_candidate_tools.py`
- **Acceptance criteria:**
  - `[BEHAVIORAL]` `research_generate_candidates` on the greenscreen fixture with a time range writes ≥1 candidate PNG plus a `candidates.json` that validates against schema v1 (all candidate `image_path`s exist on disk, IDs unique and stable across two identical runs into fresh dirs). Its `output_dir` follows the same rule as the export tools: existing non-empty dir → `invalid_input` unless `overwrite=True` (and overwrite only honored for a dir containing `candidates.json`).
  - `[BEHAVIORAL]` `research_select_candidate` with a valid ID exports a package whose `manifest.json` names the chosen candidate's timestamp; with an unknown ID returns `invalid_input` listing the valid IDs; with a missing/absent `candidates.json` returns `not_found` naming the expected path.
  - `[BEHAVIORAL]` If the source video's size or mtime no longer matches the fingerprint, `research_select_candidate` returns `invalid_input` telling the agent to re-run generate (tested by touching/replacing the file between calls).
  - `[STRUCTURAL]` `handshake.py` contains no `subprocess`/argv construction and no `@mcp.tool()`; `research_candidates.py` contains no JSON-schema/persistence logic (grep-verifiable: `json.dump` appears only in `handshake.py`).
- **Dependencies:** none

---
sub_spec_id: SS-04
phase: run
depends_on: ['SS-03']
---

### 4. One-shot run + package export tools
- **Scope:** `research_run(video_path, transcript_path=None, query=None, start_seconds=None, end_seconds=None, output_dir, obsidian=False, keep_candidates=False, overwrite=False)` — thin shell over `service.research_video` (deterministic full pipeline, auto-selects top-scored frame per region, exports package; mirrors `wvb research`); `start_seconds`/`end_seconds` map to `timestamp_ranges=[(start_seconds, end_seconds)]`. `research_export_package(candidates_dir, output_dir, obsidian=False, keep_candidates=False, overwrite=False)` — exports from an existing handshake dir without an agent selection: uses `selections` recorded in `candidates.json` if non-empty, else the deterministic top-scored candidate per region (via SS-03's public `load_handshake(candidates_dir) -> dict` rehydration helper). Both refuse an existing non-empty `output_dir` unless `overwrite=True`, and `overwrite=True` is only honored when the target dir contains a `manifest.json` or `candidates.json` (a prior research artifact) and is not under `media/raw/` or `projects/source/` — otherwise `invalid_input` regardless of the flag.
- **Files (new):**
  - `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_package.py`
  - `tests/unit/test_research_package_tools.py`
- **Acceptance criteria:**
  - `[BEHAVIORAL]` `research_run` on the fixture with a `--range`-equivalent time window and no transcript produces `output_dir/{index.md, manifest.json, screenshots/001-*.png}` and returns the manifest summary (regions, captures, errors) in the envelope.
  - `[BEHAVIORAL]` `research_export_package` on a fresh handshake dir (no selections) exports the top-scored candidate; on a dir where `select` already ran, re-exports the agent's selection.
  - `[BEHAVIORAL]` Both tools return `invalid_input` (with a suggestion to pass `overwrite=True`) when `output_dir` exists and is non-empty; with `overwrite=True` they replace it.
- **Dependencies:** SS-03 (rehydration helpers in `handshake.py`)

---
sub_spec_id: SS-05
phase: run
depends_on: ['SS-01', 'SS-02', 'SS-03', 'SS-04']
---

### 5. Registry + end-to-end integration proof
- **Scope:** Integration coverage that crosses all module boundaries. Registry check: `assert_registered` (testkit) for all ten tool names after a plain server import — proves auto-discovery picked up the three new `tools/` modules with zero `__init__.py` edits. E2E: drive the real flow with real ffmpeg against the greenscreen fixture — generate → read `candidates.json` → select a specific candidate → assert the exported package (`index.md`, schema-valid `manifest.json`, nonempty screenshot PNG whose pixel dimensions match the fixture). Marked with the existing `requires_*` skip guards so environments without ffmpeg skip rather than fail.
- **Files (new):**
  - `tests/integration/test_research_tools_e2e.py`
- **Acceptance criteria:**
  - `[STRUCTURAL]` `assert_registered` passes for all ten `research_*` tool names.
  - `[INTEGRATION]` Full handshake E2E: `research_generate_candidates` → parse `candidates.json` → `research_select_candidate(cand-001)` → package exists on disk with `index.md` + `manifest.json` + `screenshots/*.png`, and the manifest's selected timestamp equals the chosen candidate's timestamp — crossing SS-03 and SS-04 boundaries in one test.
  - `[MECHANICAL]` `uv run pytest tests/ -q` exits 0.
- **Dependencies:** SS-01, SS-02, SS-03, SS-04

## Edge Cases
- **Stale/missing handshake state** → `select`/`export` return `not_found` naming the expected `candidates.json` path; never a traceback.
- **Source video changed between generate and select** → fingerprint (size + mtime ns) mismatch → `invalid_input` instructing the agent to re-run `research_generate_candidates`.
- **Unknown candidate ID** → `invalid_input` listing the valid IDs from `candidates.json`.
- **Existing non-empty output dir** → refused with a suggestion to pass `overwrite=True` (parent-spec no-silent-overwrite rule carried into every disk-writing tool, including generate). **Overwrite is bounded:** honored only when the target contains a `manifest.json`/`candidates.json` (a prior research artifact) and is never honored under `media/raw/` or `projects/source/` — a wrong `output_dir` from an agent must not delete arbitrary directories.
- **Seek targets** (parent-spec carryover) → permissive: clamp to `[0, duration]`, record the actual extracted timestamp in the payload. Input *validation* is strict: bad paths, malformed transcripts, malformed JSON params reject with specific errors.
- **VFR source** (parent-spec carryover) → the adapters already force accurate seek and record `vfr_warning`; shells pass it through in the envelope, never strip it.
- **ffmpeg/ffprobe missing** → `missing_binary` with install hint, from the adapters' existing exception types.

## Out of Scope
- Caching/resumability (parent spec phase 5).
- `VisionFrameEvaluator` / OCR provider implementations — the agent-in-the-loop handshake intentionally substitutes for a vision provider.
- Any CLI changes (`wvb research` et al. stay as-is; tools and CLI share the same stage functions).
- Workspace/timeline integration (placing research screenshots on a Kdenlive timeline is a separate future spec).
- Changes to existing pipeline/adapter modules — `handshake.py` is the only addition under `pipelines/visual_research/`; no edits to `service.py`, `export.py`, `candidates.py`, adapters, or any `__init__.py`.
- Renaming or aliasing the existing `transcript_search` workspace tool.

## Constraints
**Musts:**
- `@tool_guard` directly under `@mcp.tool()` on every tool; envelope via `tools_helpers._ok`/`_err` (Req 4).
- All FFmpeg through existing adapters; no argv construction in shells or `handshake.py` (Req 5).
- Handshake state fully disk-persisted with stable IDs and source fingerprint (Req 3).
- Auto-discovery only — zero shared-file/`__init__.py` edits (Req 1).

**Must-Nots:**
- No silent fake success; no whole-vocabulary error imports.
- No overwrite of existing non-empty output dirs without `overwrite=True`.
- No new runtime dependency; no OpenCV; no changes to `candidates.json` schema v1 once SS-03 lands without bumping `schema_version`.
- No mutation of any source media or project file (these tools never touch `.kdenlive` files).

**Preferences:**
- Mirror underlying stage-function defaults verbatim over inventing tool-level defaults.
- Mirror `tools/transcript_markers.py` / `tools/workspace_media.py` structure for the grouped modules.
- Small envelopes: return paths + summaries, never inline image bytes.

**Escalation Triggers:**
- Any existing pipeline/adapter signature would need to change.
- `candidates.json` schema v1 proves insufficient for rehydration.
- A new runtime dependency appears necessary.

## Verification
1. `uv run pytest tests/ -q` — full suite green including the ~5 new test files.
2. Registry: testkit `assert_registered` passes for all ten `research_*` tools.
3. E2E (integration tier, real ffmpeg): generate → select → package on disk with `index.md`, schema-valid `manifest.json`, and a nonempty screenshot matching the fixture's dimensions.
4. Live smoke (optional, not gating): in a Claude session, "grab a screenshot where the reporter appears" completes using only the new tools.

## Execution Guidance
**Observe:**
- `uv run pytest tests/unit/test_research_*.py -q` after each sub-spec; full `uv run pytest tests/ -q` before claiming done.
- `uvx ruff check --select F401,F841` — clean state is zero new findings (patcher shim exceptions documented in CLAUDE.md do not apply here).
- Tool registration: a module that imports but registers zero tools means a decorator-order mistake — check `@mcp.tool()` above `@tool_guard`.

**Orient:**
- Mirror `edit_mcp/server/tools/transcript_markers.py` / `tools/workspace_media.py` for grouped-module structure, import style, and docstring voice.
- Error message/suggestion voice per `docs/research/2026-07-03-hardening/error-contract.md`.
- The parent pipeline's tests (`tests/unit/test_research_export.py`, `test_research_regions.py`) show the hermetic patterns for building regions/candidates without real video.

**Escalate When:** (mirrors spec Constraints)
- Any existing pipeline/adapter signature would need to change.
- `candidates.json` schema v1 proves insufficient for rehydration.
- A new runtime dependency appears necessary.

**Shortcuts (Apply Without Deliberation):**
- `@mcp.tool()` → `@tool_guard` → validate → call stage function → `_ok`/`_err`. No other shell shape.
- Import only the specific error constructors used; catch adapter exceptions (`FFmpegNotFound` → `missing_binary`, etc.) explicitly before the `tool_guard` backstop.
- Paths in envelopes use forward slashes; return paths + summaries, never image bytes.

## Decision Authority
**Agent Decides Autonomously:** parameter docstrings, test case design, internal helper naming in `handshake.py`, exact envelope `data` key names (within `_ok` conventions), fallback-region implementation details.
**Agent Recommends, Human Approves:** any change to the ten tool names or their parameter names (they are the public agent-facing API), any addition beyond the ten tools, any `candidates.json` schema change after SS-03 lands (requires `schema_version` bump).
**Human Decides:** scope changes (new tools/features), altering the parent pipeline's behavior, adding runtime dependencies.

## War-Game Results
**Most Likely Failure:** schema drift between `FrameCandidate` and `candidates.json` across future model changes → mitigated: entries are the serialized model + `schema_version`; round-trip asserted in SS-03 tests.
**Scale Stress:** long/UHD sources → bounded by the parent spec's hard candidate ceiling per region; extraction adapters already carry timeouts. Degrades gracefully.
**Dependency Risk:** ffmpeg/ffprobe missing → `missing_binary` with install hint; CI installs ffmpeg in the `full` job so the integration tier actually runs.
**Maintenance Assessment:** strong — one new logic module with a documented schema, thin shells matching 200+ existing tools, E2E test doubles as usage documentation.

## Evaluation Metadata
- Evaluated: 2026-07-21 (/forge-evaluate, full_context scope)
- Cynefin Domain: Clear (one Complicated element: handshake state contract)
- Assumptions: 6 audited — 3 confirmed, 2 strongly supported, 1 mitigated via committed default (ASM-5 region-resolution seam)
- Critical Gaps: 0 · Important: 1 (resolved) · Suggestions: 2 (both applied)
- Red team: 2026-07-21 — 3 CRITICAL + 4 ADVISORY, all patched (`docs/specs/2026-07-21-visual-research-mcp-tools-redteam-report.md`)

## Phase Specs

Refined by `/forge-prep` on 2026-07-21.

| Sub-Spec | Phase Spec |
|----------|------------|
| 1. Media read-only tools module | `docs/specs/visual-research-mcp-tools/sub-spec-1-research-media-tools.md` |
| 2. Transcript read-only tools module | `docs/specs/visual-research-mcp-tools/sub-spec-2-research-transcript-tools.md` |
| 3. Handshake pipeline module + generate/select tools | `docs/specs/visual-research-mcp-tools/sub-spec-3-handshake-pipeline-and-tools.md` |
| 4. One-shot run + package export tools | `docs/specs/visual-research-mcp-tools/sub-spec-4-run-and-export-tools.md` |
| 5. Registry + E2E integration proof | `docs/specs/visual-research-mcp-tools/sub-spec-5-registry-and-e2e-integration.md` |

Index: `docs/specs/visual-research-mcp-tools/index.md`
