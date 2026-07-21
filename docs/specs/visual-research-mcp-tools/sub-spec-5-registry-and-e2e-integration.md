---
type: phase-spec
sub_spec_id: SS-05
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
phase: run
depends_on: ['SS-01', 'SS-02', 'SS-03', 'SS-04']
dispatch: factory
---

# SS-05. Registry + end-to-end integration proof

This IS the integration sub-spec for the run — it crosses every module boundary (no additional auto-generated integration sub-spec is needed).

## Shared Context
- Registry proof: a plain server import must register all ten tools via pkgutil auto-discovery — zero `__init__.py` edits anywhere in the diff.
- E2E flow (real ffmpeg, `requires_ffmpeg_ffprobe`): `research_generate_candidates` → parse `candidates.json` → `research_select_candidate(["cand-001"])` → exported package on disk.
- Fixture: `tests/fixtures/media_generated/greenscreen_reporter_720.mp4`; probe its geometry with the existing `probe_frame_geometry` (or `probe_media`) to assert screenshot dimensions match the fixture.
- These tools are NOT timeline-affecting — no melt render proof is required; the ffmpeg/ffprobe oracle tier is the correct depth (per master spec Context).

## Implementation Steps

### Step 1. Registry test
Write `tests/integration/test_research_tools_e2e.py`, first test: `assert_registered` for all ten names — `research_probe_video`, `research_extract_frame`, `research_extract_frame_burst`, `research_detect_scenes`, `research_transcript_search`, `research_transcript_context`, `research_generate_candidates`, `research_select_candidate`, `research_run`, `research_export_package`.
Run: `uv run pytest tests/integration/test_research_tools_e2e.py -q` → passes if SS-01..04 landed (this sub-spec runs last).

### Step 2. Full handshake E2E test
Add the E2E test: generate (time range on the greenscreen fixture, fresh tmp dir) → read `candidates.json`, take `candidates[0]["id"]` → select it → assert package dir contains `index.md`, schema-valid `manifest.json`, ≥1 nonempty `screenshots/*.png` whose pixel dimensions match the fixture; assert the manifest's selected timestamp equals the chosen candidate's `timestamp_seconds`; assert `selections` in `candidates.json` now contains the chosen ID.
Run: `uv run pytest tests/integration/test_research_tools_e2e.py -q` → all pass.

### Step 3. Whole-suite gate, commit
`uv run pytest tests/ -q` exits 0 — no regression to the existing suite. `uvx ruff check --select F401,F841` zero new findings.
Commit: `factory(SS-05): research tools registry + E2E integration proof [factory-managed]`

## Interface Contracts
- Implements contracts from Sub-specs 1, 2, 3, 4 (tool-name sets; candidates.json schema v1).

## Verification Commands
- Integration: `uv run pytest tests/integration/test_research_tools_e2e.py -q`
- Full: `uv run pytest tests/ -q`
- Lint: `uvx ruff check --select F401,F841`

## Checks

| Criterion | Type | Command |
|-----------|------|---------|
| E2E test file exists | [STRUCTURAL] | `test -f tests/integration/test_research_tools_e2e.py \|\| (echo "FAIL: tests/integration/test_research_tools_e2e.py not found" && exit 1)` |
| Full suite passes | [MECHANICAL] | `uv run pytest tests/ -q 2>&1 \| tail -1 ; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: test suite failed" && exit 1)` |
| No __init__.py edits in the diff | [MECHANICAL] | `! git diff --name-only main \| grep -q "__init__.py" \|\| (echo "FAIL: __init__.py was edited — auto-discovery contract violated" && exit 1)` |
