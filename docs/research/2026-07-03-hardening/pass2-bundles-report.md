# Hardening Pass 2 — adversarial fault injection (`server/bundles/` + pipelines)

Scope owned: `server/bundles/` (61 tools), `pipelines/` (non-kdenlive-adapter),
`adapters/{ffmpeg,render,stt}/`, new tests. Untouched: `server/tools/`,
`errors.py`, `adapters/kdenlive/`.

Contract (unchanged from pass 1): every tool fails **gracefully but loudly** —
`status=error` + machine-readable `error_type` + actionable `suggestion`, never a
traceback in the payload, never a silent fake success. Additionally verified on
failure: **project files byte-unchanged**, **`media/raw` never written**, **no
half-written output left in `media/processed`**.

## Baseline / final

- Baseline (start): `4001 passed, 1 skipped, 0 failed`.
- New permanent suite: `tests/integration/test_faults_bundles.py` — **70 tests, all green**.
- Final full suite: **`4159 passed, 1 skipped, 0 failed`** (`uv run pytest tests/ -q`).

## Carry-over fixes (from pass1-bundles-report §pipeline-level defects)

1. **Untyped `{success:False,"error":str}` pipeline dicts → now carry a stable
   `error_type`.** Added to: `stabilize._fail`, `denoise_video`,
   `loudnorm_two_pass._fail` (media_unreadable for measurement, operation_failed
   for apply), `silence_segment`, `thumbnail_sheet` (media_unreadable),
   `review_loop` (5 sites: missing_file / operation_failed / invalid_input /
   media_unreadable), `ai_mask` (4 sites), `audio_sync` (4 sites: missing_binary
   / missing_file / invalid_input / media_unreadable). New bundle helper
   `server/bundles/_pipeline_errors.error_from_pipeline_result()` maps the dict
   to the `errors.py` contract with a per-type suggestion; the 8 consuming
   bundles now call it instead of the untyped `_err(result["error"])`.
2. **`motion_track.extract_locator_frames` bare `RuntimeError` split** into
   `FfmpegUnavailable(RuntimeError)` (binary missing → `missing_binary`),
   `FrameExtractionError(RuntimeError)` (ffmpeg ran, decoded nothing →
   `media_unreadable`), plus an explicit `FileNotFoundError` for a missing
   source. The `motion_track` bundle maps each to the matching contract type.
3. **`slideshow`/`clip_dupes` bundle `_probe_duration` no longer silently
   returns `None` on all errors.** Now logs a WARNING and distinguishes:
   missing file · ffprobe-not-on-PATH · ffprobe-nonzero-exit · unparseable
   duration string.

Additionally, the ffmpeg-backed bundles (stabilize, denoise, loudnorm, silence)
now catch the pass-1 typed `FFmpegNotFound`/`FFmpegTimeout` and map them to
`missing_binary` / `operation_failed`, and clean up partial output on failure.

## Breaks found by fault injection, and fixed

| # | Tool / pipeline | Fault that exposed it | Defect | Fix |
|---|---|---|---|---|
| 1 | `scene_detect.detect_scenes` | text-file-`.mp4`, zero-byte `.mp4` | **FALSE SUCCESS** — ignored ffmpeg return code, always `success` with `cut_count:0` | check rc + stats; nonzero-and-empty → `media_unreadable`; `FileNotFoundError` → `missing_binary`; bundle passes `error_type` through |
| 2 | `slideshow` bundle | folder of corrupt PNGs | **SERVER HANG** — no subprocess timeout; a corrupt image on an `-loop 1` input makes ffmpeg spin forever | `SLIDESHOW_RENDER_TIMEOUT` (1800s, test-shrinkable) + `TimeoutExpired`/`FileNotFoundError` handling + partial-output cleanup |
| 3 | `qc_scan.scan_clip` | text-file-`.mp4` | **FALSE ALL-CLEAR** — undecodable clip rated a perfect 5/5 `usable` | detect unreadable (rc≠0 ∧ no stats ∧ no duration) → verdict `flagged`, reason `unreadable`, rating drops; adds `unreadable` field |
| 4 | `stabilize` bundle | audio-only `.wav` to a video tool | **FALSE SUCCESS** — vidstab "stabilised" a stream with no video into a bogus track | up-front `has_video_stream()` probe → `media_unreadable` before any render |
| 5 | 11 bare `_err(...)` sites | missing source / empty dir / garbage JSON / out-of-range index | **loud but untyped** (no `error_type`) | enriched to carry `error_type` (+ `valid_range` where relevant), message text preserved |

Enriched-untyped sites (#5): `clip_preview` (missing_file), `beat_grid`
(missing_file), `clip_dupes` (missing_file + not_found), `qc_scan`/`loudness_scan`
(not_found), `timeline_audio` (`_validate_track`→invalid_index; keyframes→
invalid_input; EQ bands→bad_json_param), `speed_ramp` (track/clip→invalid_index),
`motion_track.subject_track` (missing_file).

## Fault matrix (what was injected, by category)

| Fault class | Tools exercised | Verdict |
|---|---|---|
| wrong-format media (text named `.mp4`) | 10 single-source media tools (stabilize, denoise, loudnorm, silence, thumbnail_sheet, scene_detect, clip_preview, beat_grid, review_loop.thumbnail_generate, ai_mask) | all structured error; `media/raw` untouched |
| zero-byte media | same 10 | all structured error |
| missing source | same 10 + audio_sync + qc/loudness | all structured error, typed |
| audio-only → video tool | stabilize | media_unreadable (was false success) |
| video-only → audio tool | audio_sync | structured error |
| corrupt clip to batch scanner | qc_scan, loudness_scan | flagged `unreadable` / `measured:0` — loud, no false all-clear |
| empty dir | slideshow, clip_dupes | structured error (not_found) |
| corrupt/truncated images | slideshow (timeout guard), clip_dupes | structured error, no hang, no partial |
| garbage keyframe/sources/cuts/bands JSON | speed_ramp, multicam (assemble+switch), timeline_audio (volume+eq), motion_track.subject_zoom | bad_json_param / invalid_input; project byte-unchanged |
| corrupt project | speed_ramp, timeline_audio (volume+pan), motion_track.subject_zoom, multicam.switch | structured error; project byte-unchanged |
| out-of-range track/clip index | timeline_audio.track_volume, motion_track.subject_zoom, speed_ramp | invalid_index (+ valid_range); byte-unchanged |
| TOCTOU (source deleted after gate, before ffmpeg) | stabilize | structured error, no crash |
| read-only `media/processed` (chmod 0o500, restored) | denoise | structured error, no traceback |
| melt absent (PATH stripped in-test) | motion_track.subject_track + `resolve_engine` unit | missing_dependency / TrackerUnavailable |
| subprocess timeout (1ms override on a slow filter) | ffmpeg runner | `FFmpegTimeout` raised — pass-1 timeout plumbing fires |
| carry-over error_type pass-through | denoise, audio_sync, motion_track typed excs | correct `error_type` surfaced |
| probe-duration logging | slideshow/clip_dupes `_probe_duration` | WARNING logged; missing vs unparseable distinguished |

## Cleanup-behaviour verdicts

- **stabilize / denoise / loudnorm**: partial/zero-byte output in
  `media/processed` removed on failure — verified
  (`test_failed_render_leaves_no_partial_output`).
- **slideshow**: partial output removed on timeout/nonzero exit — verified.
- **ai_mask**: matte is built in a `TemporaryDirectory` and only the final file
  is moved out on success; added defensive `cleanup_partial_output` on the
  failure path.
- **`media/raw`**: never written by any processing tool — asserted after every
  wrong-format/zero-byte run.
- **project files**: byte-identical after every failed project-tool run —
  asserted across corrupt-project, garbage-JSON, and invalid-index cases.

## Notes / residual

- melt-absent is proven representatively (subject_track + a `resolve_engine`
  unit test); the pass-1 `TrackerUnavailable → missing_dependency` mapping
  already covers the other melt-dependent bundles.
- "disk-space" is exercised via the read-only-output-dir proxy (cheap,
  deterministic); a true `ENOSPC` is not simulated.
- No files committed.
