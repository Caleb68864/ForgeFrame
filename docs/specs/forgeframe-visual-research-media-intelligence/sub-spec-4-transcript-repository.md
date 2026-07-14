---
sub_spec_id: SS-04
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-04 — Transcript parsers + repository

## Context
Parse SRT/VTT/JSON (+ existing `Transcript`) into `TranscriptSegment[]`; provide query/slice/search.
Generation stays in `whisper_engine` — read-only here. The `sample.json` fixture MUST contain a
segment matching the SS-10/SS-11 query ("reporter on camera") within the greenscreen video duration.

## Implementation Steps (TDD)
1. **Fixtures:** author `tests/fixtures/transcripts/sample.srt`, `sample.vtt`, `sample.json` with
   3–4 segments; ensure one segment text contains "reporter on camera" with times inside the
   fixture-video duration.
2. **Failing test** `tests/unit/test_transcript_repository.py`: `parse_transcript` on each fixture
   yields correct start/end/text; `TranscriptRepository.search("Reporter")` is case-insensitive;
   `.overlapping(a,b)` returns intersecting segments; `.context_around(t,n)` returns ±n window;
   `.merge_adjacent(gap)` merges near-adjacent.
3. **Run to fail:** `uv run pytest tests/unit/test_transcript_repository.py -q`.
4. **Implement** `adapters/transcript/parsers.py::parse_transcript(path)` (extension+sniff detection)
   and `pipelines/transcript_repository.py::TranscriptRepository` with `search`, `overlapping`,
   `context_around`, `merge_adjacent`.
5. **Run to pass:** `uv run pytest tests/unit/test_transcript_repository.py -q`.
6. **Commit:** `factory(SS-04): transcript parsers + repository [factory-managed]`

## Interface Contracts
- **Owner** of `parse_transcript` and `TranscriptRepository`. Consumed by SS-05, SS-10.
- **Requires:** `TranscriptSegment` (SS-01).

## Verification Commands
- `uv run pytest tests/unit/test_transcript_repository.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| parsers expose parse_transcript | [STRUCTURAL] | `grep -q "def parse_transcript" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/transcript/parsers.py \|\| (echo "FAIL: parse_transcript missing" && exit 1)` |
| repository defines TranscriptRepository | [STRUCTURAL] | `grep -q "class TranscriptRepository" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/transcript_repository.py \|\| (echo "FAIL: TranscriptRepository missing" && exit 1)` |
| transcript fixtures exist | [STRUCTURAL] | `test -f tests/fixtures/transcripts/sample.json && test -f tests/fixtures/transcripts/sample.srt && test -f tests/fixtures/transcripts/sample.vtt \|\| (echo "FAIL: transcript fixtures missing" && exit 1)` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_transcript_repository.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: repo tests" && exit 1)` |
