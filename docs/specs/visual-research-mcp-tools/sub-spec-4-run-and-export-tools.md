---
type: phase-spec
sub_spec_id: SS-04
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
phase: run
depends_on: ['SS-03']
dispatch: factory
---

# SS-04. One-shot run + package export tools

Two tools in one module. `research_run` mirrors `wvb research` (deterministic full pipeline). `research_export_package` exports from an existing handshake dir without requiring an agent selection.

## Shared Context
- `service.research_video(source, transcript=None, query=None, ..., timestamp_ranges=None, config=None, *, output_dir=None, obsidian=False, keep_candidates=False) -> ResearchManifest` (`service.py:189`) — already probes, selects regions, generates/scores/dedupes candidates, auto-selects top-ranked, and exports. Region errors are isolated into `manifest.errors`.
- `start_seconds`/`end_seconds` tool params map to `timestamp_ranges=[(start_seconds, end_seconds)]`. Transcript path parsed via `parse_transcript` when provided.
- `research_export_package` consumes SS-03's `load_handshake(candidates_dir) -> dict` (contract owner: SS-03): uses `selections` if non-empty, else the deterministic top-scored candidate per region; builds captures; calls `export_package`.
- Overwrite bound (same as SS-03): refuse existing non-empty `output_dir` without `overwrite=True`; honor overwrite only when the target contains `manifest.json`/`candidates.json`; never under `media/raw/` or `projects/source/`; otherwise `invalid_input` with a suggestion.
- Envelope payload for `research_run`: manifest summary — region count, capture count, output paths, `errors` list. Paths forward-slashed. Never inline image bytes.

## Implementation Steps

### Step 1. Failing tests
Write `tests/unit/test_research_package_tools.py`: `assert_registered("research_run", "research_export_package")`; `research_run` on the greenscreen fixture with `start_seconds`/`end_seconds` and no transcript (marked `requires_ffmpeg_ffprobe`) produces `output_dir/{index.md, manifest.json, screenshots/001-*.png}` and returns the manifest summary; existing non-empty `output_dir` → `invalid_input` suggesting `overwrite=True`; `overwrite=True` against a non-research directory → `invalid_input` (destructive-path guard); export on a fresh handshake dir (no selections) exports the top-scored candidate; export after a select re-exports the agent's selection.
Run: `uv run pytest tests/unit/test_research_package_tools.py -q` → fails.

### Step 2. Create the module
Create `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_package.py`:
- `research_run(video_path: str, transcript_path: str | None = None, query: str | None = None, start_seconds: float | None = None, end_seconds: float | None = None, output_dir: str, obsidian: bool = False, keep_candidates: bool = False, overwrite: bool = False) -> dict`
- `research_export_package(candidates_dir: str, output_dir: str, obsidian: bool = False, keep_candidates: bool = False, overwrite: bool = False) -> dict`
Both validate the overwrite bound BEFORE any disk write.
Run: step-1 tests pass.

### Step 3. Full-suite + lint gate, commit
`uv run pytest tests/ -q` green; `uvx ruff check --select F401,F841` zero new findings.
Commit: `factory(SS-04): research one-shot run + export tools [factory-managed]`

## Interface Contracts

### load_handshake (consumed)
- Implements contract from Sub-spec 3.

### research_package tool names
- Direction: Sub-spec 4 -> Sub-spec 5
- Owner: Sub-spec 4
- Shape: registered tool names `research_run`, `research_export_package`

## Verification Commands
- Unit: `uv run pytest tests/unit/test_research_package_tools.py -q`
- Full: `uv run pytest tests/ -q`
- Lint: `uvx ruff check --select F401,F841`

## Checks

| Criterion | Type | Command |
|-----------|------|---------|
| Module exists with two @mcp.tool() functions | [STRUCTURAL] | `[ $(grep -c "@mcp.tool()" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_package.py) -eq 2 ] \|\| (echo "FAIL: expected exactly 2 @mcp.tool() in research_package.py" && exit 1)` |
| Consumes SS-03's load_handshake (no re-rolled persistence) | [STRUCTURAL] | `grep -q "load_handshake" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_package.py \|\| (echo "FAIL: research_package.py does not use load_handshake" && exit 1)` |
