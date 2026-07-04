# Consistency Sweep — Structure Notes (append-only)

Observations accumulated across the 5-pass consistency effort. Each pass appends;
nothing here is rewritten. Baseline at start of Pass 1: `514f69d`,
4203 passed / 1 skipped, ~60.9k LOC across 243 modules under
`workshop-video-brain/src/workshop_video_brain/`.

---

## Pass 1 (2026-07-03) — duplication census + shared-helper extraction

Extraction-only pass. No public API renames, no tool signature changes, no
behavior change (log-text wording was normalized in two places where the only
test assertions are loose substring checks — noted below).

### Duplication census (extracted this pass)

| Family | Copies found | Extracted to | Notes / LOC |
|---|---|---|---|
| Per-effect wrapper body (parse→build filter→snapshot→insert→snapshot→serialize) | 22 generated modules + generator template | `tools_helpers.apply_simple_effect()` + slimmed `effect_wrapper_gen` template; regenerated all wrappers | Wrappers 1956→802 LOC (−1154). Byte-identical regen preserved (SR-10). |
| ffprobe duration, JSON `-show_streams` variant (prefers video-stream duration, silent) | 2 (`clip_place`, `multicam`) — byte-identical | `adapters/ffmpeg/probe.probe_duration_seconds()` | `multicam._probe_duration_seconds` kept as import alias (monkeypatched in `test_workflow_failures`). |
| ffprobe duration, `format=duration` variant (logs loudly) | 2 (`clip_dupes`, `slideshow`) — identical modulo log prefix wording | `adapters/ffmpeg/probe.probe_format_duration(path, *, log_label)` | Local `_probe_duration` names retained as thin delegates (imported by `test_faults_bundles`). Log wording normalized; only loose `"missing"`/`"probe"` substring asserts exist. |
| Media source finder: explicit path or newest in `media/raw` | 4 (`stabilize`, `ai_mask`, `media_denoise_video`, `audio_normalize_two_pass`) — identical modulo ext-set constant | `tools_helpers.find_source_or_latest(ws, source, extensions)` | Per-module `_VIDEO_EXTS`/`_MEDIA_EXTS` preserved and passed in. Local fn names kept as delegates. |
| `_find_workspace_root(start)` — walk up for `workspace.yaml` | 3 (`proxy_wiring`, `subtitle_track`, `guides`) — identical | `tools_helpers.find_workspace_root()` | Local names kept as delegates. |
| `_make_filter(mlt_service, clip_ref, props)` — simple `<filter>` XML | 3 (`masking`, `shape_alpha`, `paper_cutout`) — identical | `pipelines/_common.make_filter_xml()` (new module) | Removed now-unused `import ET` from all 3. |
| `_seconds_to_mmss(seconds)` — `M:SS` formatter | 2 (`youtube_analytics`, `publishing`) — identical | `pipelines/_common.seconds_to_mmss()` | Local names kept as delegates (imported by unit tests). |
| Local `_ok`/`_err` response envelopes | 1 (`bundles/titles`) — identical to `tools_helpers` | import from `tools_helpers` | trivial. |

**Helpers created/extended**
- `edit_mcp/server/tools_helpers.py` (+137): `apply_simple_effect`,
  `find_source_or_latest`, `find_workspace_root`.
- `edit_mcp/adapters/ffmpeg/probe.py` (+74): `probe_duration_seconds`,
  `probe_format_duration`.
- `edit_mcp/pipelines/_common.py` (new, ~48): `make_filter_xml`,
  `seconds_to_mmss`. (First tenant of the pipeline-local shared module.)
- `effect_wrapper_gen.py` template slimmed (−~90 net), emits a thin wrapper
  delegating to `apply_simple_effect`.

**Call sites migrated:** 22 wrapper modules + generator; 4 duration-probe sites;
4 media-finder bundles; 3 workspace-root bundles; 3 filter-XML pipelines;
2 mmss pipelines; 1 titles envelope. **LOC delta (tracked files):** +507 / −1742
(net −1235); +~48 new `_common.py`; overall ≈ **−1187 LOC**.

### Suspicious near-misses (same intent, different values/behavior — DO NOT unify yet)

1. **`tools/audio.py::_find_audio_file` vs the 4 bundle finders.** Same shape but
   the audio variant adds `return p if p.is_file() else None` on the explicit-path
   branch (bundles return `p` unconditionally). Behavior differs — left separate.
   Candidate: add an `require_file: bool` flag to `find_source_or_latest` in a
   later pass.
2. **`_resolve_project` (`proxy_wiring`, `subtitle_track`) uses `files[-1]`** —
   lexicographic "latest", i.e. the exact `_v10 < _v2` bug that
   `tools_helpers.latest_project()` was created to fix. 2 copies. Unifying to
   `latest_project` would be a behavior *fix*, not a no-op — flag for pass 2/3
   decision, do not fold silently.
3. **`production_brain/skills/voiceover.py::_seconds_to_timestamp`** is
   behaviorally identical to `seconds_to_mmss` but lives in a different top-level
   package (`production_brain`) and has a different name. Cross-package extraction
   deferred (pipelines/_common is under edit_mcp).
4. **Two duration-probe shapes were intentionally kept separate** (not unified):
   `probe_duration_seconds` (silent, prefers video-stream duration, 30s timeout)
   vs `probe_format_duration` (loud logging, container `format=duration`,
   no timeout). Different contracts; both now canonical in `probe.py`.
5. **`transitions.py`** has 3 inline `working_copies.glob("*.kdenlive")` +
   `latest_project(...)` sequences that nearly match `_load_latest_project` but
   differ in error/return handling. Candidate consolidation, pass 2.

### Larger structural duplicates observed (not yet touched — pass 2/3 candidates)

- **`insert_overlay_clip` (overlay_looks) ≈ `insert_take_clip` (vo_loop)** — 13
  normalized statements identical. Largest untouched cross-file body dup. Needs
  semantic diff before extraction.
- **`_parabolic_peak` (beat_grid) ≈ `_parabolic_refine` (audio_sync)** —
  sub-sample peak interpolation; part of the mono-PCM/beat family flagged in the
  brief. Also check mono-PCM decode duplication between these two modules.
- **`_check_unit` (overlay_looks, color_wash)** and **`_match_strength`
  (broll_suggestions, auto_mark)** — small identical helpers.

### Structural observations for the eventual restructuring opinion (pass 5)

- `server/tools_helpers.py` is becoming the de-facto shared kernel: it now spans
  workspace validation, response envelopes, latest-project selection, project
  load/save, filter-XML building, effect application, and media finders. This
  mixes ≥4 domains in one file; pass 5 should consider splitting into
  `_workspace.py` / `_responses.py` / `_effects.py` (imports are the only churn).
- `has_video_stream` lives in `server/bundles/_pipeline_errors.py` but is a pure
  probe — it arguably belongs beside `probe_duration_seconds` in
  `adapters/ffmpeg/probe.py`. Left in place this pass (would move a public-ish
  name); flag for pass 2.
- The `pipelines/<x>.py` (pure logic) + `server/bundles/<x>.py` (I/O envelope)
  split is consistently applied (clip_place, multicam, slideshow, timeline_audio,
  subtitle_track, guides, proxy_wiring, review_loop, …). This is a healthy
  seam — restructuring should preserve it.
- `effect_catalog.py` is 4521 LOC (largest module by far, mostly data). Not a
  duplication concern; noted for size awareness only.
- Deterministic generated code (`pipelines/effect_wrappers/*`) is protected by a
  byte-identical regeneration test, so template-level extraction is safe and
  repeatable — the right lever for that family rather than editing the 22 files.
