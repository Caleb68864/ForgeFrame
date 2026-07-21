---
type: phase-spec
sub_spec_id: SS-02
master_spec: "docs/specs/2026-07-21-visual-research-mcp-tools.md"
phase: run
depends_on: []
dispatch: factory
---

# SS-02. Transcript read-only tools module

Two read-only tools over the existing transcript parsers and repository. Thin shells only.

## Shared Context
- Stage functions: `parse_transcript(path) -> list[TranscriptSegment]` (`edit_mcp/adapters/transcript/parsers.py:128`, dispatches `.json`/`.srt`/`.vtt`); `TranscriptRepository` (`edit_mcp/pipelines/transcript_repository.py`) — `search(term, case_insensitive=True) -> list[TranscriptSegment]` (UNSCORED — do not invent a relevance score) and `context_around(timestamp, seconds) -> list[TranscriptSegment]`.
- Result shape per segment: `(id, start_seconds, end_seconds, text)` in transcript order. Serialize via the segment model's `SerializableMixin` round-trip.
- Fixtures (tracked): `tests/fixtures/transcripts/sample.json`, `sample.srt`, `sample.vtt` — one behavioral case per format.
- Same registration/envelope/error patterns as SS-01 (see exemplar `tools/transcript_markers.py`). Strict validation: unparseable transcript → `invalid_input` naming the parser's cause; missing file → `missing_file`. Zero-hit search → `_ok` with empty list, NOT an error.

## Implementation Steps

### Step 1. Failing tests
Write `tests/unit/test_research_transcript_tools.py`: `assert_registered("research_transcript_search", "research_transcript_context")`; search for a word present in exactly one `sample.json` segment returns that segment with correct timestamps; zero-hit query returns `status == "success"` with empty list; repeat the happy-path search once each against `sample.srt` and `sample.vtt`.
Run: `uv run pytest tests/unit/test_research_transcript_tools.py -q` → fails.

### Step 2. Create the module
Create `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_transcript.py`:
- `research_transcript_search(transcript_path: str, query: str, limit: int = 10) -> dict` — parse → `TranscriptRepository.search(query)` → first `limit` segments in transcript order.
- `research_transcript_context(transcript_path: str, timestamp_seconds: float, window_seconds: float = 30.0) -> dict` — parse → `context_around(timestamp_seconds, window_seconds)`, ordered by start time; a timestamp beyond the transcript returns an empty list plus a message noting the transcript's end time.
Run: step-1 tests pass.

### Step 3. Error-path tests, then complete behaviors
Add tests: malformed transcript file → `invalid_input` envelope naming the parse failure; missing file → `missing_file`; context at a beyond-end timestamp → empty list + end-time message. Implement until green.

### Step 4. Full-suite + lint gate, commit
`uv run pytest tests/ -q` green; `uvx ruff check --select F401,F841` zero new findings.
Commit: `factory(SS-02): research transcript read-only tools [factory-managed]`

## Interface Contracts
### research_transcript tool names
- Direction: Sub-spec 2 -> Sub-spec 5
- Owner: Sub-spec 2
- Shape: registered tool names `research_transcript_search`, `research_transcript_context` (SS-05 asserts via `assert_registered`)

## Verification Commands
- Unit: `uv run pytest tests/unit/test_research_transcript_tools.py -q`
- Full: `uv run pytest tests/ -q`
- Lint: `uvx ruff check --select F401,F841`

## Checks

| Criterion | Type | Command |
|-----------|------|---------|
| Module exists with two @mcp.tool() functions | [STRUCTURAL] | `[ $(grep -c "@mcp.tool()" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_transcript.py) -eq 2 ] \|\| (echo "FAIL: expected exactly 2 @mcp.tool() in research_transcript.py" && exit 1)` |
| No invented relevance score in results | [STRUCTURAL] | `! grep -q "\"score\"" workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools/research_transcript.py \|\| (echo "FAIL: research_transcript.py invents a score field" && exit 1)` |
