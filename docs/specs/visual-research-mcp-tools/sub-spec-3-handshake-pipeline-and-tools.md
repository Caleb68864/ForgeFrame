---
type: phase-spec
sub_spec_id: SS-03
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
phase: run
depends_on: []
dispatch: factory
---

# SS-03. Handshake pipeline module + generate/select tools

The two-call agent handshake. ALL state logic lives in the new pipeline module `handshake.py`; the tools module is a thin shell. This is the only sub-spec that adds logic.

## Shared Context
- **Decided (region resolution):** `handshake.py` builds a `ResearchQuery` and calls the **public** `select_regions(repo, query, config)` (`pipelines/visual_research/regions.py:238`). With no transcript/query/range, it constructs the bounded uniform-sampling fallback region itself (mirror `service._fallback_region`, `service.py:108`, ~15 lines). In-package imports of `service` privates are permitted; **edits to `service.py` are forbidden**.
- Stage functions consumed: `probe_media`, `generate_candidates(video_path, region, source, config)` (`candidates.py:39`), `FrameScorer` (`scoring.py:196`), `deduplicate` (`dedup.py:155`), `export_package(manifest, output_dir, obsidian, keep_candidates, config)` (`export.py:50`).
- Models (`core/models/visual_research.py`): `FrameCandidate` already has UUID `candidate_id`, `region_id`, `timestamp_seconds`, `image_path`, `extraction_method`, `metrics`. The handshake's `cand-NNN` IDs are a **selection alias** mapped over the serialized model — entries embed the serialized `FrameCandidate` verbatim plus `id` (`cand-NNN`) and string `region_id`.
- `candidates.json` schema v1: `{"schema_version": 1, "source": {"path", "size_bytes", "mtime_ns"}, "query", "regions": [...], "candidates": [...], "selections": []}`. IDs zero-padded, ordered by (region index, timestamp).
- Hermetic test patterns: `tests/unit/test_research_export.py` and `test_research_regions.py` show how to build regions/candidates without real video.
- Safety: `json.dump` may appear ONLY in `handshake.py` (grep-enforced). No `subprocess` in `handshake.py`. Overwrite bound: refuse existing non-empty dirs without `overwrite=True`; honor overwrite only when the target contains `candidates.json`/`manifest.json` and never under `media/raw/` or `projects/source/`.

## Implementation Steps

### Step 1. Failing pipeline tests (hermetic)
Write `tests/unit/test_research_handshake.py` against `pipelines/visual_research/handshake.py` directly (no MCP layer): schema v1 shape assertions; `cand-NNN` ordering by (region index, timestamp); fingerprint recorded (path, size_bytes, mtime_ns); `load_handshake` round-trips what `generate_handshake` wrote; unknown ID in `select_from_handshake` raises/returns error listing valid IDs; fingerprint mismatch detected after touching the file; selections persisted into `candidates.json` before export.
Run: `uv run pytest tests/unit/test_research_handshake.py -q` → fails (module missing).

### Step 2. Implement `handshake.py`
Create `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/handshake.py` with three public functions:
- `generate_handshake(video_path, *, transcript_path=None, query=None, start_seconds=None, end_seconds=None, output_dir, max_candidates=None, config=None) -> dict` — probe → resolve regions (decided default above) → `generate_candidates` → `FrameScorer` → `deduplicate` → write `<output_dir>/candidates/*.png` + `<output_dir>/candidates.json`; returns the manifest dict.
- `load_handshake(candidates_dir) -> dict` — rehydrate + validate schema_version + source fingerprint. Missing `candidates.json` → raise a specific exception the shell maps to `not_found` naming the expected path; fingerprint mismatch → exception mapped to `invalid_input` telling the agent to re-run generate.
- `select_from_handshake(candidates_dir, candidate_ids, *, output_dir=None, obsidian=False, keep_candidates=False, overwrite=False) -> dict` — `load_handshake` → validate IDs (unknown → error listing valid IDs) → **persist chosen IDs into `selections` in `candidates.json`** → build `ResearchCapture`s (one per selected candidate) → `export_package`. `candidate_ids` is a list of one or more.
Run: step-1 tests pass.

### Step 3. Failing shell tests, then the tools module
Write `tests/unit/test_research_candidate_tools.py`: `assert_registered("research_generate_candidates", "research_select_candidate")`; generate on the greenscreen fixture with a time range (marked `requires_ffmpeg_ffprobe`) writes ≥1 PNG + schema-valid `candidates.json`, stable IDs across two runs into fresh dirs; generate into an existing non-empty dir → `invalid_input` unless `overwrite=True` (overwrite honored only when the dir contains `candidates.json`); select with valid ID exports a package whose `manifest.json` names the chosen candidate's timestamp; unknown ID → `invalid_input` listing valid IDs; missing `candidates.json` → `not_found` naming the expected path; source touched between calls → `invalid_input` advising re-generate.
Create `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_candidates.py` exposing `research_generate_candidates` and `research_select_candidate` as thin shells over the two pipeline functions.
Run: `uv run pytest tests/unit/test_research_candidate_tools.py -q` → all pass.

### Step 4. Full-suite + lint gate, commit
`uv run pytest tests/ -q` green; `uvx ruff check --select F401,F841` zero new findings.
Commit: `factory(SS-03): visual research agent handshake [factory-managed]`

## Interface Contracts

### load_handshake
- Direction: Sub-spec 3 -> Sub-spec 4
- Owner: Sub-spec 3
- Shape: `load_handshake(candidates_dir: str | Path) -> dict` — rehydrated, validated handshake state (schema v1 dict)

### candidates.json schema v1
- Direction: Sub-spec 3 -> Sub-specs 4, 5
- Owner: Sub-spec 3
- Shape: `{"schema_version": 1, "source": {path, size_bytes, mtime_ns}, "query", "regions", "candidates" (serialized FrameCandidate + id/region_id), "selections"}`

### research_candidates tool names
- Direction: Sub-spec 3 -> Sub-spec 5
- Owner: Sub-spec 3
- Shape: registered tool names `research_generate_candidates`, `research_select_candidate`

## Verification Commands
- Unit: `uv run pytest tests/unit/test_research_handshake.py tests/unit/test_research_candidate_tools.py -q`
- Full: `uv run pytest tests/ -q`
- Lint: `uvx ruff check --select F401,F841`

## Checks

| Criterion | Type | Command |
|-----------|------|---------|
| No subprocess/argv construction in handshake.py | [STRUCTURAL] | `! grep -q "subprocess" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/handshake.py \|\| (echo "FAIL: subprocess in handshake.py" && exit 1)` |
| No @mcp.tool() in handshake.py | [STRUCTURAL] | `! grep -q "@mcp.tool" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/handshake.py \|\| (echo "FAIL: mcp.tool in pipeline module" && exit 1)` |
| json.dump only in handshake.py (not the shell) | [STRUCTURAL] | `! grep -q "json.dump" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_candidates.py \|\| (echo "FAIL: persistence logic leaked into shell" && exit 1)` |
| load_handshake exported | [STRUCTURAL] | `grep -q "def load_handshake" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/handshake.py \|\| (echo "FAIL: load_handshake missing" && exit 1)` |
