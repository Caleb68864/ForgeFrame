---
sub_spec_id: SS-02
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-02 — FFmpeg runner pre-input seek + frame extraction adapter

## Context
`run_ffmpeg` (`edit_mcp/adapters/ffmpeg/runner.py`) currently emits `ffmpeg -y -i <input> <args>
<output>`. Add an additive `pre_input_args` param so `-ss` can precede `-i`. Build `frames.py` on
top. Reuse `probe_media` (`adapters/ffmpeg/probe.py`) for `is_vfr`. Keep `timeout=` +
`TimeoutExpired` handling (repo FFmpeg-hygiene rule). Video-only fixture:
`tests/fixtures/media_generated/greenscreen_reporter_720.mp4`.

## Implementation Steps (TDD)
1. **Failing test** `tests/integration/test_frame_extraction_smoke.py`: assert `run_ffmpeg(...,
   pre_input_args=["-ss","1.0"])` places `-ss 1.0` before `-i` in `.command`; assert
   `run_ffmpeg` with no `pre_input_args` yields the byte-identical legacy command;
   assert `extract_frame(fixture, 0.5)` writes a non-empty PNG whose probed w/h match the
   candidate; assert `extract_frame_burst(fixture, 0.0, 0.4, interval_seconds=0.1, max_frames=5)`
   returns 5 chronological candidates with unique timestamps.
2. **Run to fail:** `uv run pytest tests/integration/test_frame_extraction_smoke.py -q`.
3. **Modify** `runner.py`: add `pre_input_args: list[str] | None = None`; build
   `cmd = ["ffmpeg"] + (["-y"] if overwrite else []) + (pre_input_args or []) + ["-i", str(input_path)] + args + [str(output_path)]`.
4. **Implement** `adapters/ffmpeg/frames.py`: `extract_frame` (accurate seek `-ss` after `-i`
   for `quality="high"`; `pre_input_args=["-ss",t]` for `"fast"`; probe `is_vfr` → force accurate,
   set `vfr_warning`), `extract_frame_burst` (widen interval when count>max_frames, dedupe,
   chronological), `extract_centered_burst`. Each returns `FrameCandidate` with `extraction_method`
   and actual timestamp in metadata.
5. **Run to pass:** `uv run pytest tests/integration/test_frame_extraction_smoke.py -q`.
6. **Regression:** `uv run pytest tests/ -q` (existing runner tests unchanged).
7. **Commit:** `factory(SS-02): pre_input_args runner + frame extraction adapter [factory-managed]`

## Interface Contracts
- **Owner** of `run_ffmpeg(pre_input_args=...)` and `extract_frame/extract_frame_burst/
  extract_centered_burst`. Consumed by SS-03, SS-06.
- **Requires:** `FrameCandidate` (SS-01), `probe_media`/`MediaAsset` (existing).

## Verification Commands
- `uv run pytest tests/integration/test_frame_extraction_smoke.py -q`
- `uv run pytest tests/ -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| runner has pre_input_args param | [STRUCTURAL] | `grep -q "pre_input_args" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/runner.py \|\| (echo "FAIL: pre_input_args missing" && exit 1)` |
| frames.py exposes the three fns | [STRUCTURAL] | `grep -Eq "def extract_frame\b" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/frames.py && grep -q "def extract_frame_burst" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/frames.py && grep -q "def extract_centered_burst" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/frames.py \|\| (echo "FAIL: frame fns missing" && exit 1)` |
| smoke tests pass | [MECHANICAL] | `uv run pytest tests/integration/test_frame_extraction_smoke.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: frame smoke" && exit 1)` |
| no regression | [MECHANICAL] | `uv run pytest tests/ -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: regression" && exit 1)` |
