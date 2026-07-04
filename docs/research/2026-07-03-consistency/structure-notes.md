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

---

## Pass 2 (2026-07-03) — API/signature + units consistency

Live registry: **201 tools** (unchanged). Baseline before pass: 4203 passed / 1
skipped (the lone external `test_clip_place_render` "failure" in the initial
run was interference from in-flight edits during the 6-min baseline; passes
clean in isolation). Post-pass: unit+integration 4144 passed; external green;
count still 201.

### Job 1 — behavior fixes flagged by pass 1 (real bugs)

- **`_resolve_project` lexicographic `files[-1]` `_v10<_v2` bug** — FIXED in
  `bundles/proxy_wiring.py` and `bundles/subtitle_track.py`. Both now import and
  use `tools_helpers.latest_project()` (numeric `_v<N>` selection) for the
  empty-`project_file` fallback. Regression test added to each suite
  (`test_proxy_attach.py::test_resolve_project_picks_highest_version_not_lexicographic`
  and the twin in `test_subtitle_attach.py`) — both create `_v2`+`_v10` working
  copies and assert `_v10` is chosen.
- **3 inline glob+latest sequences in `tools/transitions.py`** → consolidated to
  `tools_helpers._load_latest_project(workspace_path)` (replaced glob +
  `if not files: return err(...)` + `latest_project` + `parse_project`; removed
  the now-unused local `parse_project` import ×3; top-level import switched
  `latest_project`→`_load_latest_project`). Error contract preserved: the empty
  case now raises `FileNotFoundError` (same message) caught by the tool's outer
  `from_exception` backstop → `missing_file` envelope; hardening tests only
  assert `assert_contract`, still green. Inline workspace validation kept (it
  returns the tuned `invalid_input`/`missing_file` messages before the load).

### Job 2 — signature-convention census (extracted from live registry)

**First param (entry-point) — 177/201 lead with `workspace_path`.** The
non-`workspace_path`-first tools split into two groups:
- *Legitimately not workspace tools* (operate on a URL / library / file / name):
  youtube `channel_url`/`video_url`, `broll_library_search` (`query`),
  `broll_library_tag` (`source_path`), `effect_info` (`name`), `color_analyze` /
  `qc_check` (`file_path`), publishing `vault_path`, `forgeframe_init`
  (`projects_root`), `workspace_create` (`title`), `pattern_extract` (`query`),
  `project_new` (`title`), ideation (`brain_dump`). Not deviations.
- *Genuine order deviations — project-file-first addressing* (operate on a
  project but lead with the project path, deriving the workspace via
  `find_workspace_root`): `guide_add`, `guide_list`, `guide_remove`,
  `effect_pan_zoom`, `title_card_add`, `publish_chapters`
  (`project_file_or_workspace`). Coherent subfamily; **DOCUMENTED, not
  reordered** — reordering positional params breaks callers.
- Of the 93 tools carrying both `workspace_path` and `project_file`, only 2 put
  `project_file` later than 2nd: `render_final_tool`
  (`workspace_path, profile, output_name, project_file`) and `vo_plan`
  (`workspace_path, script_file, wpm, project_file`). In both `project_file` is
  optional and follows the primary required args — sensible; DOCUMENTED.

**Naming-variant families (majority convention → deviations).** Decision: the
brief's example `track_index` rename turned out to be a *semantic* difference,
not a naming inconsistency, so **0 renames / 0 `@param_alias` decorators were
warranted**; all deviations DOCUMENTED. Details:

| Concept | Majority (count) | Deviations (count) | Verdict |
|---|---|---|---|
| video-track index | `track` (77) | `track_index` (2: `track_mute`,`track_visibility`), `target_track` (1: `effect_light_leak`), `overlay_track` (3), `track_a`/`track_b` (3+3), `base_track`,`from_track`,`to_track`,`match_track`,`audio/music/voice_track` | **Keep all.** `track_index` in `track_mute/visibility` indexes **all** project tracks (incl. audio); the majority `track` indexes **video playlists only** (via `_resolve_playlist`) — different concept, the name signals it. `target_track`/`overlay_track`/`track_a`/`track_b` are contextual pair-members. No confusing dup to fix. |
| clip index within a track | `clip` (56, effect/mask/composite tools) | `clip_index` (18, clip-editing + a few effect bundles), `overlay_clip_index`,`in/out_clip_index`,`match_clip_index`,`segment_index` | **Same concept, two names** = the one genuine cross-cutting naming dup. But 56+18 spread is a big-bang either way; the brief says bias to minimal churn. **DOCUMENTED for pass 5**; not renamed. (If ever unified: alias `clip`↔`clip_index` via a `@param_alias` shim rather than positional break.) |
| media source | `source` (13) | `source_path` (1 `broll_library_tag`), `source_file` (1 `project_match_source`), `source_a/b`,`source_dir`,`source_or_dir` | Contextual; DOCUMENTED. |
| out name | `output_name` (9: render/mask/thumbnail/media_* /subtitles_burn_in) | `output_dir` (1) | `output_name` is the clear majority; no `output_path` param exists. Consistent. |
| time position (seconds) | `at_seconds` (7) | `timestamp_seconds` (1 `transitions_apply_at`), `split_at_seconds` (1), `in/out_seconds`,`start/end_seconds`,`start/end_frame` | Names all self-document their unit (see Job 3). `timestamp_seconds` could be `at_seconds` but is unambiguous; DOCUMENTED. |

**No `@param_alias` decorator was added** (would be unused infra — nothing was
renamed). If pass 5 elects the `clip`/`clip_index` unification, that is the
place to introduce it.

### Job 3 — UNITS (the last open §1.3 item) — FIXED-with-scope

**One canonical conversion helper.** Moved the half-up
`seconds_to_frames(seconds, fps)` (`floor(seconds*fps + 0.5)`, raises on
negative time / non-positive fps) from `pipelines/clip_place.py` into
`pipelines/_common.py` as the single source of truth; `clip_place` now
re-exports it (back-compat for `clip_place.seconds_to_frames` callers/tests).

**Migrated ~42 ad-hoc conversion sites across 18 files** off `int(t*fps)`
truncation and bare/`int(round(...))` rounding onto the canonical helper:
`server/tools/clips_nle.py` (8: clip_insert/split/trim/gap), `tools/transitions.py`
(2), `pipelines/{title_cards,replay_generator,selects_timeline,titles,review_loop,
multicam,clip_preview,slideshow,speed_ramp(3),timeline_audio(3),assembly(9)}`,
`adapters/kdenlive/patcher_intents.py` (1), `server/bundles/{titles,image_overlay(2),
motion_track(2),pan_zoom}`. Truncation→half-up is a ≤1-frame correctness change
only at fractional `seconds*fps`; whole-second/integer-fps values (nearly all
test vectors) are identical, so full suite stayed green. Negative-guarded sites
(`>= 0 else -1`, `max(0.0, ...)`) preserved; `timeline_audio` attack/release
routed through the helper as `ms/1000.0` seconds.

**Left intentionally (documented):**
- `pipelines/guides.py::seconds_to_frames` and
  `pipelines/vo_loop.py::seconds_to_frames` — thin front-ends that resolve a
  `DEFAULT_FPS` fallback then round; **separate tested contract** (bad-fps →
  DEFAULT_FPS, e.g. `vo.seconds_to_frames(2.0,0)==50`). The canonical helper
  *raises* on bad fps, so these keep their own bodies. Candidate: have them
  delegate the final math to `_common.seconds_to_frames` once fps is resolved
  (pass 3+); low value, deferred.
- `adapters/kdenlive/serializer.py:143` `int(fps*1000),1000` — fps→rational, not
  a time conversion.

**Docstrings state units via the param NAME itself** — census of genuine
time-typed params: **28 `*_seconds`, 16 `*_frames`, 2 `*_ms`**, 0 bare/ambiguous.
Only 1 (`mask_generate_and_apply.max_frames`) isn't named in its own docstring,
and it's documented by delegation ("Extra args beyond `mask_generate`"). Unit
self-documentation is effectively complete; no docstring edits needed for units.

→ Recommend marking §1.3 units item **FIXED-with-scope** in the plan (conversion
unification landed; public units unchanged).

### Job 4 — result-shape census

- **Envelope is uniform**: every tool returns `{"status": "...", "data"/"message"}`
  via `tools_helpers._ok`/`_err` (or the richer `errors.err` family for errors).
  No flat/no-envelope success returns found (the 3 files with an inline
  `"status": "success"` are `tools_helpers` (the `_ok` definition itself) plus
  `slideshow`/`split_screen`, which route through `_ok`).
- **`snapshot_id` is consistently present on project-mutating tools.** The
  `create_snapshot` (25 files) vs `snapshot_id` count gap is fully explained by
  the **before/after** pattern: each mutating tool takes an unreturned
  `before_*` safety snapshot AND a returned post-write snapshot whose
  `.snapshot_id` is surfaced in the `_ok` payload. Verified proxy_attach/detach,
  subtitles_attach, masked_wipes (both), split_screen — all surface it.
  Read-only tools (`proxy_status`, `*_list`) and render/output tools
  (`subtitles_burn_in`) correctly omit it. **No safe-additive fix needed** — the
  convention already holds. Documented for pass 5 (nothing to normalize).

### Job 5 — docstring format

- **0 tools with a missing docstring.** 9 terse one-liners, all
  `effect_frei0r_*`/`effect_grain` generated wrappers of form
  `"Name -- short description."` plus `ping` — each has a valid one-line summary;
  not "worst offenders", left as-is (regenerating the wrapper template is the
  right lever, not hand-editing).
- Units are stated by param name (Job 3); error behavior is centralized in the
  `errors.py` structured-error helpers so per-tool notes are rarely needed. No
  docstring rewrites performed — nothing crossed the "worst offender" bar.

### Deltas / carry-forward for pass 5

- `clip` vs `clip_index` (56 vs 18) is the one real cross-cutting naming dup left
  standing — the candidate for a `@param_alias`-backed unification if churn is
  ever justified.
- `guides`/`vo_loop` `seconds_to_frames` wrappers could delegate their final
  int-math to `_common.seconds_to_frames` (keep the fps-fallback front-end).
- Project-file-first entry-point subfamily (guides + `effect_pan_zoom` +
  `title_card_add` + `publish_chapters`) is a deliberate addressing style, not a
  bug — but it's the one place the `workspace_path`-first convention bends.
