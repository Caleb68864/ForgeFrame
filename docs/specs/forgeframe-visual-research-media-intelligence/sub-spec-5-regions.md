---
sub_spec_id: SS-05
phase: run
depends_on: ['SS-01', 'SS-04']
dispatch: factory
wave: 3
---

# SS-05 — Research region selector

## Context
Turn keyword matches / explicit segment IDs / timestamp lists / ranges into bounded
`ResearchRegion[]`. Windowing defaults: pre 3.0, post 5.0, max 30.0, merge gap 2.0 (from
`ResearchConfig.windowing`). Creates the `visual_research` package.

## Implementation Steps (TDD)
1. **Failing test** `tests/unit/test_research_regions.py`: a keyword hit at `t` → region
   `[t-pre, end+post]` clamped to max, `source_method` in {query, transcript}, non-empty `reason`;
   two hits within merge gap → one merged region unioning `transcript_segment_ids`; explicit
   timestamps without transcript → `manual_timestamp` regions.
2. **Run to fail:** `uv run pytest tests/unit/test_research_regions.py -q`.
3. **Implement** `pipelines/visual_research/__init__.py` (package) and `regions.py::select_regions(
   repo, query, config) -> list[ResearchRegion]`.
4. **Run to pass:** `uv run pytest tests/unit/test_research_regions.py -q`.
5. **Commit:** `factory(SS-05): research region selector [factory-managed]`

## Interface Contracts
- **Owner** of `select_regions`. Consumed by SS-06, SS-10.
- **Requires:** `ResearchRegion`, `ResearchQuery`, `ResearchConfig` (SS-01); `TranscriptRepository` (SS-04).

## Verification Commands
- `uv run pytest tests/unit/test_research_regions.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| regions.py exposes select_regions | [STRUCTURAL] | `grep -q "def select_regions" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/regions.py \|\| (echo "FAIL: select_regions missing" && exit 1)` |
| visual_research package exists | [STRUCTURAL] | `test -f workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/__init__.py \|\| (echo "FAIL: package __init__ missing" && exit 1)` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_research_regions.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: region tests" && exit 1)` |
