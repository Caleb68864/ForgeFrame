---
sub_spec_id: SS-09
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-09 — Manifest + research package export

## Context
Write the `research/` package: copy selected frames to `screenshots/`, generate `NNN-slug.ext`
filenames (zero-padded, safe slug, traversal-safe, de-collided), write `manifest.json`
(`manifest_version="1.0"`, relative asset paths + separate absolute source path, sanitized
`ResearchConfig` in `processing.configuration`, no secrets) and `index.md`. Obsidian mode reuses
`production_brain/notes/writer.py::NoteWriter.create` — no parallel note writer. Guard against
overwriting an existing output dir without an explicit flag.

## Implementation Steps (TDD)
1. **Failing test** `tests/unit/test_research_export.py`: a manifest with two captures writes
   `index.md`, `manifest.json`, `screenshots/001-*.png` + `002-*.png`; `index.md` embeds relative
   image paths + timestamp + excerpt + selection reason; slug rejects `../` traversal and
   de-collides duplicate titles; `manifest.json` has `manifest_version`, relative asset paths, a
   separate absolute source path, `processing.configuration`, and no key matching `/api[_-]?key|secret|token/i`.
2. **Run to fail:** `uv run pytest tests/unit/test_research_export.py -q`.
3. **Implement** `pipelines/visual_research/export.py::export_package(manifest, output_dir,
   obsidian=False, keep_candidates=False) -> ResearchManifest` + slug/filename helper. Obsidian
   path delegates to `NoteWriter`.
4. **Run to pass.**
5. **Commit:** `factory(SS-09): manifest + research package export [factory-managed]`

## Interface Contracts
- **Owner** of `export_package` + slug/filename helper. Consumed by SS-10.
- **Requires:** `ResearchManifest`/`ResearchCapture`/`ResearchConfig` (SS-01); `NoteWriter` (existing).

## Verification Commands
- `uv run pytest tests/unit/test_research_export.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| export.py exposes export_package | [STRUCTURAL] | `grep -q "def export_package" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/export.py \|\| (echo "FAIL: export_package missing" && exit 1)` |
| export delegates Obsidian to NoteWriter | [STRUCTURAL] | `grep -qi "NoteWriter\|production_brain.notes" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/export.py \|\| (echo "FAIL: export not reusing NoteWriter" && exit 1)` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_research_export.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: export tests" && exit 1)` |
