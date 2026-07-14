---
sub_spec_id: SS-08
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-08 — Perceptual deduplication

## Context
Collapse near-identical candidates within a region (optionally across final captures), keeping the
highest-ranked of a cluster. Default hash = pHash on numpy arrays (dHash acceptable); Hamming ≤
`ResearchConfig.deduplication.threshold` (8). Never deletes candidate image files; records
`perceptual_hash` on each candidate.

## Implementation Steps (TDD)
1. **Failing test** `tests/unit/test_deduplication.py`: two near-identical frames collapse to one
   (higher-ranked kept); two distinct frames both survive; the source image files still exist on
   disk after dedup; each candidate has a `perceptual_hash`.
2. **Run to fail:** `uv run pytest tests/unit/test_deduplication.py -q`.
3. **Implement** `pipelines/visual_research/dedup.py::deduplicate(candidates, threshold, rank_key)
   -> tuple[list[FrameCandidate], dict]`; guarded numpy/Pillow imports.
4. **Run to pass.**
5. **Commit:** `factory(SS-08): perceptual deduplication [factory-managed]`

## Interface Contracts
- **Owner** of `deduplicate`. Consumed by SS-10.
- **Requires:** `FrameCandidate` (SS-01); rank order from `FrameScorer.rank` (SS-07, via `rank_key`).

## Verification Commands
- `uv run pytest tests/unit/test_deduplication.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| dedup.py exposes deduplicate | [STRUCTURAL] | `grep -q "def deduplicate" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/dedup.py \|\| (echo "FAIL: deduplicate missing" && exit 1)` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_deduplication.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: dedup tests" && exit 1)` |
