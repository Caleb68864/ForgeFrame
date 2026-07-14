---
sub_spec_id: SS-03
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-03 — FFmpeg scene-change detection adapter

## Context
Detect scene changes via FFmpeg `select='gt(scene,threshold)',showinfo` (null muxer), parse
`pts_time` from stderr, enforce min-gap, fall back to bounded uniform sampling when none found.
Route through the shared FFmpeg exec path; keep `timeout=`/`TimeoutExpired`. Returns
`SceneChange` (SS-01).

## Implementation Steps (TDD)
1. **Failing test** `tests/integration/test_scene_detection_smoke.py`: on the greenscreen fixture,
   `detect_scene_changes(fixture, start_seconds=0, end_seconds=…)` returns `list[SceneChange]`
   within range and spaced ≥ `minimum_gap_seconds`; on a short static range with a very high
   threshold (forcing no detections), returns a bounded non-empty uniform sample.
2. **Run to fail:** `uv run pytest tests/integration/test_scene_detection_smoke.py -q`.
3. **Implement** `adapters/ffmpeg/scene.py::detect_scene_changes(video_path, start_seconds=None,
   end_seconds=None, threshold=0.30, minimum_gap_seconds=1.0) -> list[SceneChange]`: build the
   ffmpeg filtergraph, run via the shared subprocess helper with `timeout=`, regex `pts_time:(\d+\.?\d*)`
   from stderr, apply min-gap, uniform fallback across `[start,end]` at a bounded count.
4. **Run to pass:** `uv run pytest tests/integration/test_scene_detection_smoke.py -q`.
5. **Commit:** `factory(SS-03): ffmpeg scene-change detection adapter [factory-managed]`

## Interface Contracts
- **Owner** of `detect_scene_changes`. Consumed by SS-06.
- **Requires:** `SceneChange` (SS-01); shared FFmpeg exec (SS-02 optional, may use its own probe-style call).

## Verification Commands
- `uv run pytest tests/integration/test_scene_detection_smoke.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| scene.py exposes detect_scene_changes | [STRUCTURAL] | `grep -q "def detect_scene_changes" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/scene.py \|\| (echo "FAIL: detect_scene_changes missing" && exit 1)` |
| passes timeout to subprocess | [STRUCTURAL] | `grep -q "timeout" workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/scene.py \|\| (echo "FAIL: no timeout in scene.py" && exit 1)` |
| smoke tests pass | [MECHANICAL] | `uv run pytest tests/integration/test_scene_detection_smoke.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: scene smoke" && exit 1)` |
