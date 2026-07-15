# Hardening Pass 1 — `edit_mcp/server/bundles/` report

Scope: every MCP tool in `edit_mcp/server/bundles/` must fail **gracefully but
loudly** — a structured error dict (`status == "error"`) carrying a
machine-readable `error_type` and an actionable `suggestion`, never a raw
traceback, never a silent fake success. Contract adopted verbatim from
`server/errors.py` (`err()`, prebuilt constructors, `@tool_guard`, taxonomy).

## Summary

- **Bundles audited:** 36 modules / **61 tools** (100%).
- **`@tool_guard` backstop applied:** 61 / 61 tools — no tool can leak a
  traceback anymore; any uncaught exception becomes `operation_failed` with a
  one-line cause (full traceback → server log only).
- **Typed error sites:** ~197 explicit `error_type`/prebuilt-constructor returns
  (was 0 — the legacy `_err(str)` carried no `error_type`).
- **Remaining bare `_err(...)`:** ~110 low-priority custom-validation messages
  (e.g. `"mode must be 'overwrite' or 'insert'"`). These still return
  `status=error` and are backstopped by `@tool_guard`; enriching them is
  deferred to pass 2/3 as they are not representative failure modes.
- **Tests:** new `tests/integration/test_hardening_bundles.py` — **33 cases**,
  all green. Existing bundle suites stay green (300+ enriched, 0 renamed keys).

### error_type distribution across bundles
`invalid_input` 112 · `operation_failed` 46 · `missing_file` 28 ·
`missing_binary` 6 · `invalid_index` 4 · `missing_dependency` 2 ·
`bad_json_param` 2 · `corrupt_project` 2 · `not_found` 2.

## Method

1. `@tool_guard` inserted under every `@mcp.tool()` (FastMCP-safe via
   `functools.wraps`; verified all 61 tools still register + introspect).
2. Ubiquitous idioms enriched *preserving the legacy `message` text* (so the
   loose `.lower()` substring assertions in existing tests keep passing) and
   *adding* `error_type` + `suggestion` + echo fields:
   - `"Project file not found"` → `missing_file`
   - workspace/`_load` validation excepts → `invalid_input`
   - `"Snapshot failed"` + broad `except Exception` → `operation_failed(cause=exc)`
   - media `"File not found: {src}"` → `missing_file`
   - `"Workspace path is not a directory"` / `"… must be a non-empty string"` →
     `invalid_input`
3. Targeted representative enrichment per audit category (see table).

## Audit table (tool → failure modes → status)

| Bundle (tools) | Failure modes covered | Status |
|---|---|---|
| stabilize, media_denoise_video, audio_normalize_two_pass | bad workspace, missing/`File not found` source, ext-cmd fail (pipeline `{success:False}`) | fixed (`invalid_input`/`missing_file`; ext-cmd → pipeline referral) |
| slideshow | missing ffmpeg → `missing_binary`, empty image folder → `not_found`, bad resolution, ffmpeg nonzero → `operation_failed`(stderr cause) | fixed |
| titles | missing/empty project, empty text, unknown style, bad timing | fixed (`missing_file`/`invalid_input`) |
| image_overlay (overlay_insert, watermark_apply) | bad workspace/project, missing image, bad opacity/position, empty timeline | fixed |
| guides (guide_add/list/remove, publish_chapters) | missing project, neg time, no-match remove, corrupt project (was **uncaught ProjectParseError** → now backstopped) | fixed + backstop |
| qc_scan, loudness_scan, scene_detect, silence_segment, thumbnail_sheet | bad workspace, empty media set, missing source, pipeline `{success:False}` | fixed (`operation_failed`/`missing_file`) |
| clip_dupes, clip_preview | missing ffmpeg/ffprobe → `missing_binary`, bad format, <2 clips, ffmpeg nonzero → `operation_failed` | fixed |
| ai_mask (mask_generate, …_and_apply) | bad workspace, missing source, **engine missing → `missing_dependency`** (pip hint preserved), missing project | fixed |
| motion_track (locate/track/zoom) | bad workspace/project/index, **tracker missing → `missing_dependency`**, missing media | fixed |
| clip_place (place/move_to/matched) | bad workspace/project, invalid mode, out-of-range track/clip, unknown duration | fixed |
| timeline_audio (volume/pan/eq/duck) | bad workspace/project, out-of-range track, bad keyframe/EQ JSON, positive duck_db | fixed |
| speed_ramp | bad engine, bad workspace/project, bad keyframe JSON | fixed |
| multicam (assemble/switch) | **bad sources/cuts JSON → `bad_json_param`** (example shown), <2 sources, out-of-range ref/angle, audio-sync failure | fixed |
| audio_sync | missing sources, pipeline `{success:False}` | fixed |
| proxy_wiring (attach/detach/status) | non-empty/dir workspace, missing project, nothing-to-do (loud, not silent) | fixed |
| subtitle_track (attach/burn_in) | non-empty/dir workspace, missing project/SRT/media, **missing ffmpeg/melt → `missing_binary`**, melt/ffmpeg nonzero → `operation_failed` | fixed |
| masked_wipes (masked_wipe, luma_key) | missing project, non-pos duration, empty luma_file, bad track/clip; was **uncaught ProjectParseError** → now backstopped | fixed + backstop |
| split_screen | missing project, bad track list, bad layout; **uncaught ProjectParseError** → backstopped | fixed + backstop |
| shake_shadow (camera_shake, drop_shadow) | missing project, bad index, bad params; snapshot fail → `operation_failed` | fixed |
| overlay_looks (light_leak, day_to_night) | missing project/media, bad blend/opacity/index, catalog miss | fixed |
| pan_zoom | missing/empty project, **corrupt project → `corrupt_project`**, **out-of-range track/clip → `invalid_index`(valid_range)**, no rect/preset | fixed |
| zoom_whip | missing project, **corrupt project → `corrupt_project`**, bad direction → `invalid_input`, **out-of-range index → `invalid_index`** | fixed |
| rewind | missing project/index, unresolved source, ffmpeg reverse nonzero → `operation_failed`(stderr cause) | fixed |
| shape_alpha_mask | bad workspace/project/index, bad shape params | fixed |
| transcript_index (build/search/edit) | bad workspace, empty query/clip, pipeline errors | fixed (`invalid_input`/`operation_failed`) |
| shot_alignment | bad workspace, missing steps file | fixed |
| vo_loop (plan/attach/status) | bad workspace/project, **empty script → `invalid_input`**, missing take, unknown cue, no plan | fixed |
| beat_grid (music_beat_grid, markers_from_beats) | missing ffmpeg → `missing_binary`, bad sensitivity, missing source, **empty beats → `not_found`** | fixed |
| review_loop (render_review_frames, thumbnail_generate) | bad workspace, missing project/source, pipeline `{success:False}` | fixed |
| clip_dupes/clip_preview/thumbnail (analysis) | see above | fixed |

## Representative tests (`test_hardening_bundles.py`, 33 cases)

Deterministic (no ffmpeg/melt/media required — they fail before any subprocess):
nonexistent-workspace (14 tools), missing-project-file (6), corrupt-project
(pan_zoom, zoom_whip → `corrupt_project`), invalid-index (pan_zoom, zoom_whip →
`invalid_index` + `valid_range`), malformed-JSON (multicam cuts/sources →
`bad_json_param` with example), empty-input (beat markers → `not_found`, vo_plan
→ `invalid_input`), missing-source analysis tools, missing-project for
project-path tools. Every case asserts `status=error` + valid `error_type` +
non-generic `suggestion` (>12 chars) + **no `Traceback`/`File "` in payload**.

## Pipeline-level defects referred to the pipelines-hardening sibling

1. **`{success: False, "error": <str>}` result dicts are untyped.** Pipelines
   `stabilize`, `denoise_video`, `loudnorm_two_pass`, `silence_segment`,
   `thumbnail_sheet`, `review_loop`, `ai_mask`, `audio_sync` return a bare
   `error` string. The bundle can only re-wrap it as an untyped `_err`
   (backstopped, but not classified). **Ask:** add an `error_type`/`category`
   (e.g. `missing_binary` vs `media_unreadable` vs `operation_failed`) to those
   result dicts so bundles can map them precisely.
2. **`motion_track.extract_locator_frames` raises bare `RuntimeError`** for both
   "ffmpeg missing" and "decode failed" — the bundle currently classifies it as
   `invalid_input`. Splitting into `FileNotFoundError`/a typed exception would
   let the bundle emit `missing_binary` vs `media_unreadable`.
3. **`slideshow._probe_duration` / `clip_dupes._probe_duration` swallow all
   errors → `None`.** Silent; fine for optional probes but a corrupt media file
   is indistinguishable from "no duration". Consider surfacing a warning.

## Out-of-scope failures observed (NOT this pass, NOT bundles)

Baseline at start of pass: **56 failed, 3836 passed, 2 skipped**. Final runs
fluctuated **4 → 7 failed** across the session because the concurrent
`adapters/kdenlive/` serializer sibling was actively landing changes (it fixed
~52 baseline failures, then a later `qtblend` serializer change re-broke 3).

Every failing test at every measured point is in serializer/parser/render
scope and reaches `status == "success"` before failing on a render/serialize
assertion (`Unknown element <filter> preserved as opaque node`, `qtblend` vs
`affine`) — **none are in bundle scope and none involve error handling**.
Verified: filtering the full-suite `FAILED` list to anything outside
`{test_serializer_bin, test_kdenlive_bin_roundtrip, test_multicam_render,
test_transition_renders, test_effect_presets}` returns empty. My
`test_hardening_bundles.py` (33) and all existing bundle suites are green.

My changes touch only `_err(...)` return statements and add the transparent
`@tool_guard`; no success path is altered, so these serializer failures are not
attributable to this pass.
