---
sub_spec_id: SS-06
phase: run
depends_on: ['SS-02', 'SS-03', 'SS-05']
dispatch: factory
wave: 4
---

# SS-06 — Adaptive candidate generation

## Context
Per region, produce a capped `FrameCandidate[]` = anchor + uniform burst + scene-change frames,
deduped by timestamp, capped at `ResearchConfig.candidate_generation.max_raw_candidates` (30).
Static-source fallback = periodic extraction.

## Implementation Steps (TDD)
1. **Failing test** `tests/integration/test_candidate_generation_smoke.py`: for a region on the
   greenscreen fixture, `generate_candidates` returns ≤ max_raw and includes ≥1 `uniform_burst`
   candidate (and ≥1 `scene_change` when scenes exist); a static region still yields candidates
   via periodic fallback.
2. **Run to fail:** `uv run pytest tests/integration/test_candidate_generation_smoke.py -q`.
3. **Implement** `pipelines/visual_research/candidates.py::generate_candidates(video_path, region,
   source, config)`: anchor via `extract_frame`; burst via `extract_frame_burst`; scenes via
   `detect_scene_changes` + `extract_frame`; merge/dedupe/cap; tag `extraction_method`.
4. **Run to pass.**
5. **Commit:** `factory(SS-06): adaptive candidate generation [factory-managed]`

## Interface Contracts
- **Owner** of `generate_candidates`. Consumed by SS-10.
- **Requires:** `extract_frame*` (SS-02), `detect_scene_changes` (SS-03), `select_regions`/
  `ResearchRegion` (SS-05), `FrameCandidate`/`ResearchConfig` (SS-01), `MediaAsset` (existing).

## Verification Commands
- `uv run pytest tests/integration/test_candidate_generation_smoke.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| candidates.py exposes generate_candidates | [STRUCTURAL] | `grep -q "def generate_candidates" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/candidates.py \|\| (echo "FAIL: generate_candidates missing" && exit 1)` |
| smoke tests pass | [MECHANICAL] | `uv run pytest tests/integration/test_candidate_generation_smoke.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: candidate smoke" && exit 1)` |
