---
sub_spec_id: SS-10
phase: run
depends_on: ['SS-04', 'SS-06', 'SS-07', 'SS-08', 'SS-09']
dispatch: factory
wave: 5
---

# SS-10 — Research service orchestrator

## Context
Single entry point wiring the full deterministic pipeline with per-region error isolation and
partial-manifest return. No AI on the core path (OCR/vision stages skipped by default). Emits an
integration-evidence markdown artifact.

## Implementation Steps (TDD)
1. **Failing test** `tests/integration/test_research_service_smoke.py`: end-to-end on the
   greenscreen fixture + `sample.json` + query "reporter on camera", no AI, yields a
   `ResearchManifest` with ≥1 region and ≥1 capture and a valid `research/` package; a region that
   raises during extraction is recorded as a region-level error and healthy regions still return
   (partial manifest); no-transcript-no-range run does not exceed the candidate ceiling.
2. **Run to fail:** `uv run pytest tests/integration/test_research_service_smoke.py -q`.
3. **Implement** `pipelines/visual_research/service.py::research_video(source, transcript=None,
   query=None, topics=None, timestamp_ranges=None, config=None) -> ResearchManifest`: `probe_media`
   → resolve transcript (repository / transcribe-if-flagged / transcript-free) → `select_regions`
   → per-region `generate_candidates` (wrapped in try/except → region error) → `FrameScorer` →
   `deduplicate` → deterministic top-rank select → `export_package`. Write
   `tests/integration/ss10-integration-evidence.md` capturing a real run's region/capture counts.
4. **Run to pass.**
5. **Commit:** `factory(SS-10): research service orchestrator [factory-managed]`

## Interface Contracts
- **Owner** of `research_video`. Consumed by SS-11.
- **Requires:** `TranscriptRepository`/`parse_transcript` (SS-04), `generate_candidates` (SS-06),
  `FrameScorer` (SS-07), `deduplicate` (SS-08), `export_package` (SS-09), `select_regions` (SS-05),
  `probe_media`/`MediaAsset` (existing), all models (SS-01).

## Verification Commands
- `uv run pytest tests/integration/test_research_service_smoke.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| service.py exposes research_video | [STRUCTURAL] | `grep -q "def research_video" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/service.py \|\| (echo "FAIL: research_video missing" && exit 1)` |
| integration evidence written | [STRUCTURAL] | `test -f tests/integration/ss10-integration-evidence.md \|\| (echo "FAIL: ss10 evidence missing" && exit 1)` |
| integration smoke passes | [MECHANICAL] | `uv run pytest tests/integration/test_research_service_smoke.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: service smoke" && exit 1)` |
