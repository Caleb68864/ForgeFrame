# SS-10 Integration Evidence — Research Service Orchestrator

## Fixture

`tests/fixtures/media_generated/greenscreen_reporter_720.mp4` (20.02s,
video-only, no AI/OCR/vision configured).

## End-to-end run

`test_research_video_end_to_end_produces_manifest_and_package` in
`tests/integration/test_research_service_smoke.py` copies the fixture to a
temp dir, supplies an explicit `Transcript` with a segment matching the
`"drone"` query, and calls:

```python
manifest = research_video(
    video_path,
    transcript=_transcript_with_match(),
    query="drone",
    output_dir=output_dir,
)
```

Observed result (no AI/OCR/vision configured — all optional stages skipped
by default):

- `manifest.regions` >= 1 (one region resolved from the keyword match on
  `"drone"`, expanded/clamped by `select_regions`).
- `manifest.captures` >= 1, with at least one candidate frame per capture.
- A valid `research/` package was written to `output_dir`:
  - `output_dir/manifest.json` exists, `manifest_version == "1.0"`, and
    contains >= 1 capture entry.
  - `output_dir/screenshots/` contains the exported frame for each capture.
  - `output_dir/index.md` was written alongside the manifest.

## Partial-manifest behavior

`test_research_video_records_partial_manifest_on_region_error` forces the
first region's `generate_candidates` call to raise, while a second region
(from a second topic) proceeds normally. Result: `manifest.errors` records
exactly one entry with the failing `region_id` and error message, while
`manifest.captures` still contains the capture from the healthy region —
confirming region-level error isolation and a partial (not aborted) run.

## Candidate ceiling without transcript or range

`test_research_video_without_transcript_or_range_respects_candidate_ceiling`
calls `research_video` with no transcript and no query/topics/timestamp
ranges. The service falls back to a single bounded uniform-sampling region
(`source_method == "uniform_sampling"`), and the total candidate count
across all captures stays at or under
`config.candidate_generation.max_candidates_per_region`.

## Test command

```
uv run pytest tests/integration/test_research_service_smoke.py -q
```

All 3 tests pass.
