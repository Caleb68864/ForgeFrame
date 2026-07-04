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

---

## Pass 3 (2026-07-03) — layering enforcement (model → pipeline → tool)

Push-down pass: move leaked logic (XML construction, ffmpeg/ffprobe command
building, model-manipulation math) out of the thin `server/bundles` +
`server/tools` shell layer into pipelines / the ffprobe adapter / shared
`_common`. **No tool signature or behaviour changes**; every relocation keeps a
same-name delegate in the origin module (or a re-export shim). Baseline before:
4205 passed / 1 skipped (brief cited 4204; a test was added since). Live tool
count **201** (unchanged, verified via `mcp.list_tools()`).

### Job 1 — leak census (server/bundles + server/tools)

Method: enumerated every module-level `def _helper` in the shell layer and
classified its body as shell (param validation, error mapping, snapshot
bookkeeping, envelope assembly, calling a pipeline/adapter) vs **leaked** logic
(XML element construction, ffprobe/ffmpeg argv building + parsing, model-span
math done inline). Only `import xml.etree` and direct `subprocess`/ffprobe argv
in the shell layer are hard leaks; the ranked offenders were the ones carrying
those.

| Module (layer) | Leak kind | Leaked-LOC before | after | Pushed to |
|---|---|--:|--:|---|
| `bundles/zoom_whip.py` | filter-XML builder + clip-frame model read | ~24 | ~8 (delegates) | `_common.make_filter_element_xml`; `pipelines/zoom_whip.clip_frame_length` |
| `bundles/_pipeline_errors.py` | `has_video_stream` ffprobe (misfiled) | ~23 | 0 (re-export shim) | `adapters/ffmpeg/probe.has_video_stream` |
| `bundles/clip_preview.py` | `_probe_frame_geometry` ffprobe | ~22 | 1 (delegate) | `adapters/ffmpeg/probe.probe_frame_geometry` |
| `bundles/rewind.py` | `_count_audio_streams` ffprobe | ~20 | 1 (delegate) | `adapters/ffmpeg/probe.count_audio_streams` |
| `bundles/motion_track.py` | `_build_transform_xml` (ET) | ~18 | ~5 (delegate) | `_common.make_filter_element_xml` |
| `bundles/pan_zoom.py` | `_build_transform_xml` (ET) | ~16 | ~5 (delegate) | `_common.make_filter_element_xml` |
| `bundles/subtitle_track.py` | `_project_frame_count` timeline-span math | ~10 | ~4 (parse+delegate) | `pipelines/subtitle_track.timeline_frame_length` |

Also merged (pipeline-internal, Job 3): `loudnorm_two_pass._has_video_stream`
(~18→1) now delegates to the same `probe.has_video_stream`.

**Not pushed (judged shell-appropriate, documented):**
- `bundles/rewind._apply_vhs_overlay` — *composes other MCP tools*
  (`effect_glitch_stack`/`effect_oldfilm`/`effect_frei0r_scanline0r`) and
  collects their result envelopes. Tool-orchestration, not raw logic; belongs in
  the shell.
- `bundles/clip_dupes._hash_clip_phash` / `_find_phash` — the *command
  construction* + hashing/clustering already live in `pipelines/clip_dupes`
  (`frame_extract_command`, `frame_timestamps`, `dhash_from_image`,
  `cluster_by_distance`, …); the bundle only runs the subprocess and threads the
  temp-dir loop. Executing a pipeline-built argv is adapter/orchestration work.
- `bundles/subtitle_track._escape_ff` (2 lines, single call site) and the
  `tools/audio.py` / `tools/clips_nle.py` subprocess hits (ffmpeg run
  orchestration through the sanctioned runner) — below the offender bar.
- `server/tools_helpers._build_filter_xml` (server-layer XML with id
  normalization) is used by many tools and was blessed as the shared kernel in
  Pass 1; leaving it (see Pass 5 note) — it is the *richer* sibling of the two
  new `_common` builders.

### Job 2 — logic pushed down (LOC moved)

New canonical homes created/extended:
- `pipelines/_common.py` (+~85): `make_filter_element_xml` (transform/keyframe
  filter XML with `kdenlive_id` property child; `include_service_prop` flag
  covers both the pan/zoom+motion-track shape and the zoom-whip shape —
  **byte-identical** to the three hand-rolled builders, asserted at build time),
  `check_unit_interval`, `keyword_match_strength`, `parabolic_peak_offset`.
- `adapters/ffmpeg/probe.py` (+~75): `has_video_stream`, `count_audio_streams`,
  `probe_frame_geometry` — the natural home for pure ffprobe helpers, beside
  `probe_duration_seconds`/`probe_format_duration` from Pass 1.
- `pipelines/zoom_whip.clip_frame_length`, `pipelines/subtitle_track.timeline_frame_length`.

All origin call-sites keep a same-name delegate (`_build_transform_xml`,
`_filter_xml`, `_clip_frames`, `_count_audio_streams`, `_probe_frame_geometry`,
`_project_frame_count`, `_has_video_stream`) so monkeypatch targets and any
in-module references are unaffected. ET import removed from all three transform
bundles; `subprocess`/`json`/`shutil` imports dropped where they became unused
(`rewind`, `_pipeline_errors`).

### Job 3 — deferred pipeline-internal merges (from Pass 1)

- **`insert_overlay_clip` (overlay_looks) vs `insert_take_clip` (vo_loop)** — the
  13 identical normalized statements (producer-ensure → `PlacedClip` →
  `clip_place.plan_overwrite` → assign entries → return placed index) extracted
  to **`overlay_looks.append_clip_to_playlist(project, playlist, …)`** (owner).
  `insert_overlay_clip` keeps its video-playlist resolution + validation and
  calls it; `insert_take_clip` keeps its audio-playlist resolution + validation
  and delegates (importing the shared tail). `at_frame`/`duration_frames`
  validation deliberately stays in each public fn so error precedence is
  unchanged. `vo_loop` shed now-unused `Producer`/`clip_place`/`overlay_producer_id`
  imports.
- **`_parabolic_peak` (beat_grid) ≡ `_parabolic_refine` (audio_sync)** — the
  3-point sub-sample parabola extracted to **`_common.parabolic_peak_offset`**.
  `audio_sync._parabolic_refine` (kept — it is unit-tested by name) and
  `beat_grid._parabolic_peak` (imported alias) both delegate to it.
- **mono-PCM decode overlap** — *already resolved*: `beat_grid` imports
  `decode_mono_pcm` (+`energy_envelope`/`onset_envelope`) from `audio_sync`; there
  is a single copy. No action; documented.
- **`_check_unit` (overlay_looks, color_wash)** → `_common.check_unit_interval`
  (both import as `_check_unit`). **`_match_strength` (auto_mark,
  broll_suggestions)** → `_common.keyword_match_strength` (both import as
  `_match_strength`). Bodies were byte-identical (docstrings differed only).
- **`has_video_stream` relocation** — moved from `bundles/_pipeline_errors.py`
  (a misfile per Pass-1 note) to `adapters/ffmpeg/probe.py`; `_pipeline_errors`
  re-exports it so `bundles/stabilize.py`'s import is untouched.

### Job 4 — reach-around census (direct XML/model mutation vs sanctioned APIs)

Grepped the shell + pipeline layers for direct `.entries`/`.playlists`/
`.producers`/`.filters` mutation and inline `ET` outside the sanctioned modules
(`clip_place`, `patcher`, `effect_stack`, `_common` XML builders).

- **Clean after this pass:** the only inline `ET` in the shell layer was the
  three transform bundles — now routed through `_common.make_filter_element_xml`.
  No bundle mutates `.entries` directly; all placement goes through
  `clip_place.plan_overwrite` (the `target.entries = result.entries` assignments
  in `titles`/`image_overlay` assign a *clip_place engine result*, not a
  hand-rolled edit).
- **Sanctioned exceptions (documented, NOT migrated):**
  - **Model-level producer registration** in `bundles/titles.py`,
    `bundles/image_overlay.py`, `bundles/speed_ramp.py` (`project.producers.append(
    Producer(...))` for title/image/time-remap-chain producers). Blessed —
    predates the clip_place migration; there is no producer-registration pipeline
    API and placement itself already uses `clip_place`.
  - **New-track/playlist creation** in `titles`/`image_overlay` (overlay title
    track) and `multicam` (`project.playlists.append(Playlist(...))` for camera +
    program tracks). Structural track creation (the `track_add` operation), not a
    clip-placement reach-around.
  - **`speed_ramp` entry rebinding** (`entry.producer_id/in_point/out_point = …`)
    — the timeremap engine swapping a clip's producer to its chain producer; no
    `clip_place` equivalent exists for an in-place producer swap.
  - **Timeline-builder appends** (`replay_generator`, `selects_timeline`,
    `review_timeline`, `assembly`) `video/audio_playlist.entries.append(...)` —
    these *build a fresh sequential timeline from scratch*, where append is the
    natural primitive and `plan_overwrite` (an into-existing-timeline op) would be
    overkill. These live in the pipeline layer (sanctioned) and are greenfield
    construction. Left as-is.

### Verification

- Full suite `uv run pytest tests/ -q`: **4204 passed / 1 skipped** + 1 external
  render flake under load (`test_pan_zoom_render::test_transition_rect_zoom_moves_pixels`)
  that **passes isolated** — same load-flaky class as the known
  `test_clip_place_render` one (which likewise failed in the isolated external
  batch run and passed alone; both green solo). Total 4205 tests = pre-pass
  baseline (4205 passed / 1 skipped before edits). Tool count **201**
  (live `mcp.list_tools()`).
- Byte-identity of the three relocated filter-XML builders asserted against the
  original hand-rolled ET output before running the suite.

### Deltas / carry-forward for Pass 5

- **`server/tools_helpers.py` is now doubly a mixed kernel**: it still holds
  `_build_filter_xml` (server-layer XML construction with id normalization) next
  to workspace/response/effect/media helpers. With `_common` now owning three
  pipeline-layer filter builders (`make_filter_xml`, `make_filter_element_xml`)
  the id-normalizing `_build_filter_xml` is the last XML builder stranded in the
  server layer — Pass 5 should decide whether it moves down to `_common` (it is
  imported by several tools, so it is churn, not a no-op) and/or whether
  `tools_helpers` splits into `_workspace`/`_responses`/`_effects` as flagged in
  Pass 1.
- **bundles/ vs tools/ split still looks coherent** but is *not* a
  logic-vs-shell boundary — both are the thin shell; the difference is only
  "1 tool per file / auto-imported" (`bundles/`) vs "grouped multi-tool modules"
  (`tools/`). After this pass both layers are close to pure shells (validation +
  error map + snapshot + pipeline call). Pass 5 could reasonably **merge the two
  directories** (or at least document that `bundles/` = single-tool shells,
  `tools/` = grouped shells) since the leak that justified treating `bundles/`
  as "where logic hid" is now drained.
- The `_common` module has grown to ~156 LOC spanning conversions
  (`seconds_to_frames`, `seconds_to_mmss`), XML builders, validation, text
  heuristics and DSP (`parabolic_peak_offset`). Still cohesive as "pipeline-layer
  primitives" but watch for the same multi-domain drift that hit
  `tools_helpers`; a `_common/` package split (`_xml`, `_time`, `_text`,
  `_dsp`) is a Pass-5 option if it keeps growing.

---

## Pass 4 (2026-07-03) — test-suite consolidation (testkit + dedup + flake)

Owns `tests/` + conftest infra. Baseline at pass start: **4203 passed / 1
skipped + 2 render "failures"** that were load-flakes (both green isolated),
417s. Post-pass: **4200 passed / 1 skipped, 0 failures, run TWICE** (218s and
228s) — the two `-3` vs baseline `passed` is the 5 dedup deletions minus the 2
flakes-now-passing (4203+2 collected − 5 deleted = 4200 pass + the skip).

### Testkit inventory (new shared infra)

- **`tests/_testkit.py`** (309 LOC, new — importable as `from tests._testkit
  import …`; repo-root is on `sys.path` because `tests/__init__.py` exists but
  the repo root has none, so pytest prepends it):
  - `unwrap(tool)` / `tool_fn(module, name)` / `call_tool(tool, *a, **k)` — the
    `@mcp.tool()` `.fn`-unwrap dance (was copy-pasted ~40×).
  - `registered_tool_names(mcp=None)` / `assert_registered(*names, mcp=None)` —
    the FastMCP `list_tools`/`get_tools` (sync-or-coroutine, list-or-dict) probe
    (was ~7 near-identical 10-18-line blocks).
  - `make_test_clip(path, *, duration, fps, kind, size, color, freq,
    with_audio, pix_fmt)` — ffmpeg `testsrc`/`color`/`sine` synthesis.
  - `solid_color_project` / `sequence_project` / `two_track_project` /
    `color_producer` — hermetic colour-producer `KdenliveProject` builders (the
    **non-external twin** of `external/builders.py`; deliberately NOT imported
    from the external package so non-external tests don't couple to the oracle
    tier).
  - `HAVE_FFMPEG/FFPROBE/MELT` bools + `requires_ffmpeg` / `requires_ffprobe` /
    `requires_ffmpeg_ffprobe` / `requires_melt` / `requires_melt_ffmpeg` skip
    marks (canonical; assign to module `pytestmark`).
- **`tests/conftest.py`** (113 LOC, new): re-exports the skip marks; provides
  session `ffmpeg`/`ffprobe`/`melt` fixtures (skip-if-absent, return path);
  hosts the `render_retry` bounded-retry `pytest_runtest_protocol` hook (job 3).
- **`tests/integration/external/conftest.py`** (+12): `pytest_collection_modify
  items` auto-applies `@pytest.mark.render_retry` to every external item that
  requests the `melt_bin` fixture (i.e. all real-melt render tests).
- **`pyproject.toml`**: registered the `render_retry` marker.

### Files migrated (19)

Registration/`_invoke` blocks → testkit: `unit/test_{analysis_tools,
denoise_video,loudnorm_two_pass,stabilize,audio_sync,rewind_pipeline}`,
`integration/test_{zoom_whip_mcp_tool,overlay_looks_mcp_tools,
masked_wipes_mcp_tools,review_loop_tools}`. Unwrap helper → `unwrap`:
`integration/test_{proxy_attach,subtitle_attach,beat_grid_mcp,
parse_error_propagation,vo_loop_mcp,clip_place_mcp_tools}`. Project builder →
`two_track_project`/`color_producer`: `test_clip_place_mcp_tools`. Media →
`make_test_clip`: `test_clip_preview_mcp_tool`. Marker → canonical:
`test_clip_preview_mcp_tool` (`requires_ffmpeg_ffprobe`), `test_review_loop_
tools` (`requires_melt_ffmpeg`). Each verified green individually (263 tests)
and in both full runs. **LOC (tracked files): −274 / +59; new shared infra
+422** (net +207 now; tips negative as the remaining ~20 single-line
`_fn`/`_callable` unwrap helpers migrate — mechanical follow-up, left for
budget: they each save ~2 LOC and carry per-file import churn).

**Bias kept mechanical**: no assertion-strength changes; local helper names
retained as import aliases (`_invoke`, `_fn`, `_tool_names`,
`_registered_tool_names`, `_two_track_project`, `_color_prod`) so call sites and
monkeypatch targets are untouched.

### Dedup deletions — 5 tests (class: provably-equal / misplaced-duplicate)

An AST body-hash census (name+body, then body-only) over all `test_*.py` found
**exactly one** cross-file identical-body group and **zero** other ≥4-line
duplicates. Deleted the whole `TestSlugify` (4) + `TestTimestampPrefix` (1)
classes from `unit/test_paths.py` — a path-utils file that had imported
`slugify`/`timestamp_prefix` only to re-test them. `unit/test_naming.py` is the
dedicated home with a **strict superset** (14 slugify + 6 timestamp cases):
`test_lowercase`≡`test_converts_to_lowercase` and
`test_strips_special_chars`≡`test_special_chars_stripped` are byte-identical
asserts; `test_collapses_hyphens`, `test_strips_leading_trailing_hyphens`,
`test_format` are covered by decomposed test_naming cases. Coverage
provably preserved; removed the now-unused import. **No hardening/faults
deletions**: `test_faults_*` is a *stronger superset* of `test_hardening_*`
(adds byte-unchanged / no-stray-`_v` / no-snapshot / media-raw-guard asserts),
so the bodies differ — not equal-strength; kept per "when in doubt, keep."

### Flake root cause — FOUND (environmental), not a product/test bug

The "rotating external melt-render load-flake" is caused by **orphaned,
CPU-pinning render subprocesses left by earlier force-killed (SIGKILL) suite
runs**. Caught three in-flight during this pass:
- 2× `ffmpeg -y -loop 1 -t 0.24 -i <corrupt>.png … libx264` from
  `test_faults_bundles::test_slideshow_corrupt_images` (pytest-339 & -341),
  running **4h15m / 4h09m**. ffmpeg spins forever on an undecodable PNG behind
  `-loop 1` (never reaches the `-t` frame count).
- 1× unbounded `melt … -consumer avformat:…` (no `out=` cap → targets the
  tractor's ~2.1e9-frame out) from a `render_preview`/workflow test, **215 CPU-
  min**.

Each pins a full core; stacked across interrupted passes they saturated the box
(the initial 417s baseline flaked *because* ~3 cores were stolen the whole
time). Confirmed the product code is already correctly hardened — the slideshow
bundle has `SLIDESHOW_RENDER_TIMEOUT` (default 1800s, test shrinks to 5s) +
`TimeoutExpired` handling with the exact `-loop 1` spin-forever comment, and
`render.executor.execute_render` is a blocking `subprocess.run(timeout=…)`. The
leak only happens when **pytest itself is SIGKILLed mid-render** (the child
reparents to init and, on corrupt/unbounded input, never exits). It is NOT a
tmp collision (per-test `tmp_path`), NOT a shared output path (unlink + per-test
dir), NOT SDL/consumer state (avformat consumer, no display).

**Fix**: (1) killed all orphans → clean box; suite time **halved** (417s→218s),
confirming the diagnosis. (2) Belt-and-braces bounded **2-attempt retry** scoped
to real-melt render tests via the `render_retry` marker (auto-applied to
external `melt_bin` users), with a loud yellow terminal line on each retry;
verified with a synthetic probe (flake absorbed on attempt 2 = passed; a genuine
failure still FAILS after 2 attempts = not masked; unmarked tests run once). No
blanket rerun plugin.

**Two-run verdict**: flake did **NOT** reproduce as a failure in either full run
(run1: 0 retries, 0 fail; run2: 0 fail). **Recommendation for future passes: do
not `kill -9` the suite; if interrupted, sweep `pgrep -fa 'melt|ffmpeg.*-loop'`
and kill stragglers before the next run** — a single leftover pins a core and
resurrects the flake.

### Marker normalization (job 4)

`external` marker usage is consistent (whole `external/` package via
`pytestmark`). Verified `-m external` (60) and `-m "not external"` (4141)
**cleanly partition**: 60 + 4141 = 4201 = full collection, no overlap, no gap.
ffmpeg-gated integration tests now have canonical skip marks available; migrated
2 as exemplars, the rest still use equivalent inline `shutil.which` skipifs
(same skip-report text) — mechanical follow-up.

### Test-architecture observations for Pass 5

- **`tests._testkit` is now the sanctioned shared kernel** (mirrors the
  `server/tools_helpers` story on the src side). Watch for the same multi-domain
  drift: it already spans unwrap, registration, media-gen, project builders and
  gating marks. If it grows, split into `_mcp` / `_media` / `_projects` /
  `_gates`.
- **~20 single-line `_fn`/`_callable(obj)` unwrap helpers remain** un-migrated
  (budget). All are `return getattr(x, "fn", x)` → `from tests._testkit import
  unwrap as _fn`. A handful are `_callable(mod, name)` (→ `tool_fn`) or closure
  `_callable(name)` — check the arity before swapping. Pure mechanical.
- **unit-vs-integration boundary is generally clean** but leaky in spots: the
  `unit/` tests that instantiate the FastMCP singleton and assert registration
  (`test_{analysis_tools,denoise_video,loudnorm_two_pass,stabilize,audio_sync,
  rewind_pipeline}`) are really integration-flavoured (they import the whole
  server). Not moved; flagged. Conversely `test_paths.py` had *naming* tests
  (now removed) — watch for tests filed by import-convenience rather than
  subject.
- **External oracle coverage map** (60 tests, all `melt_bin`-gated → now all
  `render_retry`): render/pixel proofs for clip-place, pan/zoom, subject-zoom,
  roto, timeremap, speed-ramp, multicam, subtitle, track-audio, transitions,
  fade-luma, image-overlay, effect-visible, plus melt-accept/probe/transport/
  fixture-roundtrip smoke. Builders are `color:`-producer solids (distro-
  independent). Gaps for Pass 5: no external proof for composite blend-modes,
  masking/alpha renders (there's a non-external `test_alpha_render`), or
  audio-loudnorm end-to-end pixel/levels.
- **`external/builders.py` vs `tests/_testkit.py` now overlap** (`solid_color_
  project`/`sequence_project` are near-identical). Left separate deliberately
  (direction rule: external MAY depend on shared, shared must NOT depend on
  external). Pass 5 could collapse by having `external/builders.py` re-export
  the three builders from `_testkit` and keep only `two_video_track_project` +
  `build_filter_xml` locally.

---

## Pass 5 (2026-07-03) — restructuring opinion (synthesis only, NO code)

Deliverable: `docs/plans/2026-07-03-codebase-restructuring-opinion.md`. No source
or test files were touched this pass; this is the decision document the owner
reads to choose whether to restructure. All prior-pass carry-forwards were
resolved into verdicts there. Summary of positions:

- **Central question (layer-first vs feature-domain vs hybrid):**
  **KEEP layer-first.** Rejected the feature-domain reorg (~40-80 agent-hours,
  HIGH import-surface + test-churn risk) because its locality benefit is already
  ~90% captured by `bundles/` pkgutil auto-discovery (new feature = new
  pipeline + new bundle, both new files, zero shared-file edit) plus
  same-basename-across-layers naming, and it would collapse the proven Pass-3
  pipeline/shell seam and fail to propagate to the tier-organized test tree.
  Calibrated against the patcher split (`e7037c4`, ~3-4h) and tools split
  (`86c22c5`, ~5-8h for one package).
- **Carry-forward verdicts:** (1) do NOT merge `bundles/` into `tools/` — the
  auto-discovery is the only zero-shared-file registration path and is the
  anti-contention asset; re-document its rationale instead. (2) SPLIT
  `tools_helpers` into a package with full re-export shim (patcher pattern) and
  fold the last stranded `_build_filter_xml` into `_common` — the cleanest real
  win. (3) `_common`/`_testkit` growth = a written >250-LOC/5-domain split
  trigger, not a pre-split. (4) `production_brain` ↔ `edit_mcp` coupling
  **violates ADR 004** (module-level `production_brain`→`edit_mcp.pipelines`;
  lazy `edit_mcp`→`production_brain.skills/notes` dodging a circular import) —
  amend via a new ADR 005, no code move. (5) tests stay tier-first, do NOT
  mirror src.
- **Recommendation:** DO ~4-6 agent-hours of surgical cleanup (Phase A
  `tools_helpers` split + stranded builder; Phase B optional `tools/`
  auto-discovery to retire the one real contention point; Phase C docs/ADR-005).
  DON'T do the feature-domain or hybrid restructure. "Do nothing more" judged
  defensible — the 4 passes captured the large majority of the value.

**Notes file complete.** Baseline at Pass 1 start was `514f69d` (4203 passed / 1
skipped, ~60.9k LOC / 243 modules); at Pass 5 the tree is 244 modules / ~59.8k
LOC, 201 live tools, suite green (per Pass 4's twice-run 4200 passed / 1 skipped).
Passes 1-4 landed code (duplication drain, API/units consistency, layering
enforcement, test consolidation); Pass 5 is synthesis only. No further appends —
this document is closed.

---

## Consolidation-1 -- split the `tools_helpers` multi-domain kernel (Phase A)

Executes the opinion's Phase A (`docs/plans/2026-07-03-codebase-restructuring-opinion.md`
section 3.2 / section 4). Pure code movement, zero behavior change, patcher-split
shim pattern. Baseline suite unchanged: **4200 passed / 1 skipped**, **201 live
tools**, both before and after (twice-run post-split). `git diff --stat` confined
to `pipelines/_common.py`, `server/tools_helpers.py` (deleted), and the new
`server/tools_helpers/` package.

**Module map (new `server/tools_helpers/` package -- was 357 LOC single file).**

| Module | LOC | Names (public + private re-exported) |
|---|--:|---|
| `__init__.py` (shim) | 76 | re-exports all 19 names below; accurate `__all__` |
| `_responses.py` | 14 | `_ok`, `_err` |
| `_workspace.py` | 83 | `_validate_workspace_path`, `_require_workspace`, `find_workspace_root`, `find_source_or_latest` |
| `_projects.py` | 99 | `_VERSION_SUFFIX_RE`, `_project_version_key`, `latest_project`, `_get_video_playlists`, `_load_latest_project`, `_save_patched`, `_resolve_playlist` |
| `_effects.py` | 130 | `__wrapped_effects__`, `register_effect_wrapper`, `apply_simple_effect`, `_lookup_catalog_by_service` |
| `_xml.py` | 16 | `_build_filter_xml` (re-export from `_common`), `_VALID_COLOR_FORMATS_MSG` |
| **total** | **418** | +61 vs 357 = added module headers/docstrings only, **zero logic delta** |

`pipelines/_common.py`: **156 -> 204 LOC** (+48, the relocated `_build_filter_xml`).
Still under the section 3.3 >250-LOC / 5th-domain split trigger, but closer --
`_common` now holds three filter builders (`make_filter_xml`,
`make_filter_element_xml`, `_build_filter_xml`) plus time/text/dsp; **watch the
trigger** (xml is the 4th domain; a 5th landing or crossing 250 LOC fires the
`_common/` package split).

Intra-package deps (no cycles): `_projects`->`_workspace` (`_validate_workspace_path`);
`_effects`->`_responses`+`_workspace` (`_ok`/`_err`/`_require_workspace`);
`_xml`->`pipelines/_common`. Shim imports submodules in dependency order.

**Module-level state check.** The one stateful object is `_effects.__wrapped_effects__`
(a list `register_effect_wrapper` appends to). Single-instance semantics preserved:
the decorator and the list live in the same submodule; `register_effect_wrapper`
mutates it in place (`.append`), and the shim re-exports the *same* list object.
Verified live -- `import workshop_video_brain.server` then
`from ...tools_helpers import __wrapped_effects__` returns the populated registry
(the `test_effect_wrapper_gen` `>= 20` assertion passes).

**Importer census (~80 modules; all `from ...tools_helpers import (names)`, no
attribute-style access, so the shim covers 100%).** Frequency by name:
`_ok`/`_err` 51, `register_effect_wrapper` 45, `apply_simple_effect` 23,
`_validate_workspace_path` 21, `_require_workspace` 21, `latest_project` 16,
`_load_latest_project` 4, `find_source_or_latest` 4, `_VALID_COLOR_FORMATS_MSG` 3,
`_save_patched` 3, `_resolve_playlist` 3, `_lookup_catalog_by_service` 3,
`find_workspace_root` 3, `_build_filter_xml` 3, `__wrapped_effects__` 2,
`_get_video_playlists` 1. Importer classes: `server/tools/*` (incl.
`tools/__init__` which re-exports 7 of these into its 133-name surface, and
`effects_bundles` -> `_build_filter_xml` x5 call sites), `server/bundles/*`,
`pipelines/effect_wrappers/*` (22 generated, via `register_effect_wrapper` +
`apply_simple_effect`; `effect_wrapper_gen` template emits that import verbatim --
**no template change needed**), `pipelines/render_final`, `server/resources`,
`app/cli`, tests (`test_latest_project`, `test_effect_wrapper_gen`). **No
monkeypatch targets `tools_helpers`** -- the `_resolve_vault_root_for_tools`
monkeypatch sites live on `server.tools`, outside this surface.

**XML-builder unification verdict: NOT unified (three distinct shapes; relocated
verbatim).** The opinion said "fold `_build_filter_xml` into `_common`"; the task
asked to merge with `make_filter_xml`/`make_filter_element_xml` *only if same
shape*. They are not:
- `make_filter_xml(mlt_service, clip_ref, props)` -> root + props, **no** svc/kid
  property children.
- `make_filter_element_xml(mlt_service, kdenlive_id, clip_ref, props, *, include_service_prop=True)`
  -> root + optional svc prop + kid prop + props (`str()`-coerced), **no** id
  normalization.
- `_build_filter_xml(mlt_service, kdenlive_id, track, clip, props)` -> **id
  normalization** (avfilter./frei0r. -> kid=svc; affine+transform w/o
  transition.rect -> qtblend) + always svc + kid + props (verbatim value).

Unifying would force a signature change at every call site (tuple `clip_ref` vs
separate `track`/`clip` ints; `str()` vs verbatim; a normalize flag), violating
the pure-movement / byte-identity contract. So `_build_filter_xml` was relocated
**byte-identically** (verbatim body incl. its local `import ... as _ET`) as a
third distinct builder in `_common`, consistent with the Pass-3 decision to keep
`make_filter_xml`/`make_filter_element_xml` as separate builders. Byte-identity
asserted against 6 pre-move reference outputs (all normalization branches) plus
the two sibling builders -- **all match**; the shim's `_build_filter_xml` `is`
the `_common` function object (single definition). A future true unification (one
builder, union of features) remains *possible* but is **deferred** -- it is not
pure movement.

**Deviations from the opinion's shape: none material.** Followed the opinion's
exact 5-module naming (`_workspace`, `_responses`, `_effects`, `_projects`,
`_xml`). Placement judgment calls (opinion did not enumerate every name):
media finders (`find_workspace_root`, `find_source_or_latest`) -> `_workspace`
(path resolution); catalog lookup (`_lookup_catalog_by_service`) -> `_effects`
(serves effect application; no separate `_catalog` module created, staying within
the named 5); `_VALID_COLOR_FORMATS_MSG` -> `_xml` (its original neighbor was
`_build_filter_xml`). Nothing deferred beyond the optional future XML-builder
unification noted above. Phases B (auto-discover `tools/`) and C (ADR-005 / docs)
untouched -- out of scope for this pass.

**No commit made** (per instruction). Working tree carries the split for review.

---

## Consolidation-2 -- retire the `tools/__init__` re-export contention point (Phase B)

Executes the opinion's Phase B (`docs/plans/2026-07-03-codebase-restructuring-opinion.md`
section 3.1 / section 4): make `server/tools/__init__.py` auto-discover its
submodules (mirroring `server/bundles/__init__.py`) so a new grouped-tool module
never edits a shared file. Pure mechanism change, zero behavior change, zero
caller edits. Baseline unchanged: **4200 passed / 1 skipped**, **201 live tools**,
before and (twice-run) after.

**Before/after.** `tools/__init__.py` went **324 lines -> 85 lines**. The old file
explicitly imported all 15 submodules and hand-maintained a 139-name re-export
block + a 139-entry `__all__` (the last shared-file contention point: every new
tool module or helper required editing it). The new file has **zero** per-name
lines -- it discovers, registers, and re-exports entirely by loop.

**Approach chosen: (a) pkgutil auto-discovery + PEP 562 `__getattr__` backed by an
ownership map** (not (b) generated eager re-exports). Rationale: `__getattr__`
keeps the module namespace clean (so a real `__dict__` entry from a
`monkeypatch.setattr` naturally shadows lazy resolution -- see below), and the
name->module map is derived, not maintained. The discovery loop
(`pkgutil.iter_modules(__path__)`, skip `_`-prefixed, `import_module` for the
decorator side effect -- identical to `bundles/`) also records, for each
submodule, the names it *owns* into `_EXPORTS: dict[str, ModuleType]`:
- functions/classes where `obj.__module__ == submodule.__name__` (the
  `@mcp.tool()` decorator returns the *plain* function with `__module__` intact,
  so tool names and private helpers are all detected);
- module-level data constants (no `__module__`) matched by container type
  (`_VALID_MASK_SHAPES`/`_VALID_MASK_TYPES` tuples) -- avoids capturing shared
  framework instances like the `mcp` singleton.
Plus a 7-name `_HELPER_REEXPORTS` tuple for the helpers historically re-exported
from the sibling `tools_helpers` package (`_build_filter_xml`, `_resolve_playlist`,
`_load_latest_project`, `_save_patched`, `_get_video_playlists`,
`_lookup_catalog_by_service`, `_VALID_COLOR_FORMATS_MSG`) -- these are imported
*into* the submodules, not defined there, so ownership discovery cannot find
them; this is the one small explicit list, and it shrinks the maintained surface
from 139 to 7. `__getattr__` resolves any `_EXPORTS` name to its source module;
unknown names still raise `AttributeError` (behavior preserved). `__all__ =
sorted(_EXPORTS)`.

**Importer coverage (all kept working, zero edits).** Verified against the full
enumerated surface: `app/cli.py` (~25 lazy `from ...tools import <name>`),
`bundles/shake_shadow.py` (`_build_filter_xml`, `_playlist_clip_duration_frames`,
`_resolve_playlist`), `bundles/rewind.py` (`effect_glitch_stack`),
`scripts/smoke_test_kdenlive_mcp.py` (`from ...server import tools` + 10
`tools.<name>` attribute accesses), and ~25 test files (name imports,
`tools.<attr>` access, submodule-name imports `from ...tools import
effects_bundles`/`effects_catalog`/`keyframes` -- these resolve via the normal
import system since `import_module` sets each submodule as a package attribute).
All 139 names of the old `__all__` resolve to the same objects; the new `__all__`
is a superset of **141** (2 additive: `_masking_finalize`, `_validate_frame_range`
-- owned private helpers now auto-exposed, harmless, nothing relied on their
absence).

**Monkeypatch verdict: SAFE (module dict wins over `__getattr__`).** The
`_resolve_vault_root_for_tools` monkeypatch (`tests/integration/test_effect_presets`,
`test_stack_presets_mcp_tools`, `test_hologram_mcp_tool`, `test_color_wash_mcp_tool`)
does `monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", ...)`;
`effects_catalog` reads it back via `_tools_pkg._resolve_vault_root_for_tools()`.
Mechanics: the pre-patch `getattr` resolves via `__getattr__` (so monkeypatch's
existence check passes and records the real func); `setattr` writes the stub into
the package `__dict__`; the read-back hits the dict (not `__getattr__`) -> stub
wins; teardown restores the real func into the dict. Confirmed live (a standalone
read-through returned the patched value) and by the four presets test files
staying green.

**Zero-edit drop-in proof.** Dropped a temp `tools/zzztempdropin.py` with a dummy
`@mcp.tool()`, imported `workshop_video_brain.server` fresh: the tool was
present as a package attribute, in `__all__`, `from ...tools import`-able, and
**registered with FastMCP (202 tools)** -- all with **zero edits** to
`__init__.py`. Temp module removed; count back to 201.

**Docs check (task step 4).** No living convention states "append to
`tools/__init__`": `CLAUDE.md`, the user memory files, and the `plugin-authoring`
skill say nothing about it; only historical dated specs reference the pre-split
`server/tools.py`. Nothing to update.

**Verification.** cli import smoke (`import workshop_video_brain.app.cli`) OK;
scripts smoke parse + all 10 `tools.<name>` references resolve; full suite
`uv run pytest tests/ -q` twice-run **4200 passed / 1 skipped** (matches Pass 4
baseline); **201 live tools** before and after. `git diff` confined to
`tools/__init__.py` (this section aside). No commit made (per instruction).

---

## Consolidation-3 -- resolve the production_brain <-> edit_mcp coupling (Phase C, ADR 005)

Executes the opinion's Phase C (`docs/plans/2026-07-03-codebase-restructuring-opinion.md`
section 3.4 / section 4): document + enforce the boundary, fix the latently-broken
skill-helper import prefixes. No `production_brain`/`edit_mcp` *source* moved
(the opinion's verdict was "amend via ADR, no code move"). Baseline suite
unchanged: **4200 passed / 1 skipped** before; **4204 passed / 1 skipped** after
(+4 = the new `tests/unit/test_module_boundaries.py`).

**Coupling map (AST import-graph audit, both directions).** The coupling **runs
both ways** but is shallow and layered:
- **Forward, `production_brain` -> `edit_mcp` (2 edges):** `skills/broll.py:12`
  **module-level** -> `edit_mcp.pipelines.broll_suggestions`; `skills/pattern.py:27`
  lazy -> `edit_mcp.pipelines.pattern_brain`. Both target *pipelines* only
  (planning consumes analysis).
- **Reverse, `edit_mcp` -> `production_brain` (12 edges, ALL function-local):**
  `pipelines/new_project.py` (x7 -> `skills.{video_note,outline,script,shot_plan}`
  + `notes.updater`), `pipelines/publishing.py` (x2 -> `notes.frontmatter`),
  `server/tools/{broll,transcript_markers,assembly_titles}.py` (x3 -> `skills.
  {broll,voiceover,pattern}`). Every reverse edge is lazy *on purpose* -- a
  module-level reverse import would form an import-time cycle against the forward
  edge. This is the load-bearing smell the opinion identified.

**Decision: BLESS, not decouple (ADR 005 written).** Rationale: the coupling is
one-directional at the *layer* level (planning depends downward on analysis) with
a single deliberately-lazy reverse escape hatch for orchestration; decoupling
`new_project`'s note-generation orchestration is exactly the ~40-80h feature-domain
restructure the opinion rejected, for zero correctness gain. Blessing names the
true direction + escape hatch honestly and cheaply. **Layering:** `core <
edit_mcp.adapters < edit_mcp.pipelines < production_brain.{skills,notes} <
edit_mcp.server < app`. Two enforced rules: (1) `edit_mcp -> production_brain`
lazy-only (no module-level); (2) `production_brain` may import
`edit_mcp.pipelines/adapters/core` but **never** `edit_mcp.server`. **No reverse
edges fixed** (none needed -- all 12 already conform to Rule 1; the 2 forward
edges conform to Rule 2). `docs/adr/004-two-module-architecture.md` got a
superseded-in-part banner pointing at ADR 005; `docs/ai-handoff.md`'s stale
two-way-wall rule was rewritten to the ADR-005 layering. `CLAUDE.md` and the
`plugin-authoring` skill state no boundary claim -- nothing to update there.

**Enforcement test.** `tests/unit/test_module_boundaries.py` (4 tests, 0.47s)
walks module ASTs (no imports/side effects), classifying each edge as module-level
vs function-local via a function-nesting visitor. Asserts Rule 1, Rule 2, and a
positive characterization (every forward edge targets pipelines/adapters/core).
Proven non-no-op: the AST classifier correctly tags `broll.py:12` MODULE-level and
all 12 reverse edges + `pattern.py:27` lazy.

**Skill-helper prefix normalization (the actual code fix).** The skills-refresh
flag was real: SKILL.md Python helpers used two prefixes -- canonical
`from workshop_video_brain.production_brain.skills.X` **and** bare
`from production_brain.skills.X`. The bare form is **latently broken**: the
installed top-level package is `workshop_video_brain` (`packages =
["src/workshop_video_brain"]`), so `import production_brain` raises
`ModuleNotFoundError` -- proven at the shell. **6 latent breaks fixed** across 5
files: `ff-rough-cut-review` (review), `ff-tutorial-script` (script),
`ff-video-idea-to-outline` (outline), `ff-shot-plan` (shot_plan),
`ff-obsidian-video-note` (video_note x2). All normalized to the fully-qualified
form. Post-fix: **0** short-prefix occurrences remain; **16** canonical imports
across 12 skills. Import smoke over all 12 referenced helper modules (every
symbol) under the canonical prefix: **FAILS = 0** (all resolve, all symbols
present).

**Verification.** Full suite `uv run pytest tests/ -q`: **4204 passed / 1
skipped** (was 4200/1 + the 4 new boundary tests). New import-graph test green;
per-helper import smoke green (12/12). No commit made (per instruction).

---

## Consolidation-4 -- clear the accumulated carry-forwards (final sweep)

Executes the residual small-item carry-forwards accumulated across passes 1-5.
Owns src + tests for the scoped items only. Pure delegation / documentation, zero
behavior change. Baseline unchanged: **4204 passed / 1 skipped** before and after
(full suite twice-clean: full run 4204/1 @154s; external tier re-run green @30s,
0 flakes). External partition still cleanly partitions -- `-m external` collects
**60** (62 items, 2 deselected). No commit made.

### Carry-forward ledger -- every item closed with a verdict

1. **guides/vo_loop `seconds_to_frames` wrapper delegation** (Pass 2 §units,
   Pass 5 delta). **DONE.** Both `pipelines/guides.py` and `pipelines/vo_loop.py`
   now keep their `if fps <= 0: fps = DEFAULT_FPS` front-end and delegate the frame
   math to `_common.seconds_to_frames(float(seconds), fps)` (the canonical half-up
   helper that *raises* on bad fps; the wrapper absorbs the fallback so it never
   sees bad fps). Both import `_common` at module level. Existing tests unchanged
   and green: `test_vo_loop::test_seconds_to_frames_rounds` (incl. `(2.0,0)==50`
   fallback) and `test_guides_pipeline::TestFrameMath` (all 5 vectors +
   `test_zero_fps_falls_back`). No test vector lands on a banker's-round-vs-half-up
   `.5` boundary, so the `int(round(...))`->half-up switch is a no-op on them.

2. **Cross-package timestamp dup** (Pass 1 near-miss 3). **DONE.**
   `production_brain/skills/voiceover.py::_seconds_to_timestamp` now delegates to
   `_common.seconds_to_mmss(seconds)` (behaviourally identical M:SS formatter).
   Direction chosen per **ADR 005**: `production_brain -> edit_mcp.pipelines` is the
   blessed downward "planning consumes analysis" edge (Rule 2 allows pipelines;
   only `edit_mcp.server` is forbidden), so a **module-level** import of `_common`
   is fine -- no cycle (`_common` imports only stdlib). `test_module_boundaries`
   (all 4) stays green, confirming the new edge is compliant. NB: a *third* copy,
   `pipelines/review_timeline.py::_seconds_to_timestamp`, is **HH:MM:SS** (not
   M:SS) -- a genuinely different formatter, **not** a dup; left alone.

3. **Testkit / external-builders overlap** (Pass 4 delta). **DONE -- collapsed via
   re-export.** Direction chosen: **external MAY depend on the shared testkit;
   the shared testkit must NEVER depend on external** (the pass-4 rule). So
   `tests/integration/external/builders.py` now imports the shared constants
   (`RED`/`BLUE`/`GREEN`/`WHITE`/`BLACK`, `DEFAULT_*`, `VIDEO_TRACK`/`AUDIO_TRACK`),
   the `color_producer` helper (aliased `_color_producer`), and the byte-identical
   `solid_color_project` / `sequence_project` builders **from `tests._testkit`**,
   and keeps only the two genuinely-different builders local:
   `two_video_track_project` (two *filled* video tracks vs testkit's
   v1-filled/v2-empty `two_track_project`) and `build_filter_xml`
   (external-render-path specific). `_testkit` is a plain, side-effect-free helper
   module (no fixtures, no server import -- only `shutil.which` PATH lookups + mark
   defs), so importing it keeps the `-m external` partition clean (verified: 60
   collected, same as pass 4). Removed the now-unused `Producer` import.

4. **`_common` growth policy** (Pass 3 + Pass 5 §3.3). **DOCUMENTED, NOT split.**
   LOC = **204/205**; domains = **4** (time, XML builders x3, DSP, validation/text).
   Under the ~250-LOC / 5th-domain trigger -> document only. Wrote the growth policy
   into the `_common.py` module docstring: what belongs (small, dependency-light,
   pure, cross-cutting primitives; stdlib + `core.models` only), and the explicit
   split trigger (>250 LOC OR 5th domain -> promote to a `_common/` package split
   by domain behind a same-path `__init__` shim; do not pre-split).

5. **clip/clip_index final verdict** (Pass 2 §naming, Pass 5 §3-explicitly-not).
   **DOCUMENTED, NO renames.** Added a "Tool Parameter Naming" convention to
   `CLAUDE.md`: new tools use `clip_index`; the 56-`clip` vs 18-`clip_index` split
   is deliberate documented debt (positional rename would break every caller for
   zero functional gain); any future unification must go through a `@param_alias`
   shim, never a positional break; new tools author with `clip_index` so the newer
   convention wins by accretion. Also captured the `workspace_path`-first
   entry-point norm there. **Not** placed in `docs/.../error-contract.md` -- that
   guide is exclusively about error *messages* (`message`/`suggestion`/`error_type`),
   so a param-naming rule would be off-topic; CLAUDE.md's Conventions section is the
   apt home.

### Other carry-forwards swept (resolve / explicitly close)

- **`tools/audio.py::_find_audio_file` guard divergence** (Pass 1 near-miss 1).
  **RESOLVED.** Added a `require_file: bool = False` keyword to the canonical
  `tools_helpers.find_source_or_latest` (missing/dir explicit path -> `None` when
  set; default `False` = existing callers unchanged). `_find_audio_file` now
  delegates: `find_source_or_latest(ws, file_path, _AUDIO_EXTS, require_file=True)`
  -- byte-equivalent behaviour (the `is_file()` guard that routes a missing path to
  the loud "No audio file found" error instead of ffmpeg's banner). Extension set
  hoisted to a module `_AUDIO_EXTS` constant. `test_faults_tools` + `test_faults_
  bundles` (82) green; stabilize/denoise/two-pass/ai_mask (`require_file=False`)
  unaffected.
- **`_resolve_project` lexicographic `_v10<_v2` bug** (Pass 1 near-miss 2) --
  **CLOSED: already fixed Pass 2** (both bundles use numeric `latest_project`).
- **Two duration-probe shapes kept separate** (Pass 1 near-miss 4) -- **CLOSED:
  intentional**; different contracts (silent video-stream vs loud
  container-format), both canonical in `probe.py`.
- **`transitions.py` 3 inline glob+latest sequences** (Pass 1 near-miss 5) --
  **CLOSED: done Pass 2** (`_load_latest_project`).
- **`insert_overlay_clip`/`insert_take_clip`, `_parabolic_*`, `_check_unit`,
  `_match_strength`, mono-PCM decode, `has_video_stream` misfile** (Pass 1 larger
  dups / Pass 3 Job 3) -- **CLOSED: all done Pass 3.**
- **`tools_helpers` split + stranded `_build_filter_xml`** (Pass 1/3, Pass 5 §3.2)
  -- **CLOSED: done Consolidation-1.**
- **`bundles/` into `tools/` merge + `tools/__init__` contention** (Pass 3, Pass 5
  §3.1) -- **CLOSED: verdict NO-merge; `tools/` auto-discovery landed
  Consolidation-2.**
- **`production_brain` <-> `edit_mcp` ADR-004 drift** (Pass 5 §3.4) -- **CLOSED:
  ADR 005 + boundary test done Consolidation-3.** (This pass's item 2 adds one more
  compliant forward edge under it.)
- **Project-file-first entry-point subfamily / signature order** (Pass 2 §sig) --
  **CLOSED: intentional addressing style, documented Pass 2; no reorder** (positional
  break). CLAUDE.md now also notes the `workspace_path`-first norm.
- **`tests/_testkit.py` growth** (Pass 4, Pass 5 §3.3). **DOCUMENTED, split
  DEFERRED.** LOC = **309 / 5 domains** -- *at* the trigger. Wrote the growth policy
  + split plan (shim-backed `tests/_testkit/` package: `_mcp`/`_media`/`_projects`/
  `_gates`, `__init__` re-exports so the ~19 importers stay byte-identical) into the
  `_testkit` docstring. Executing the split is a self-contained mechanical change
  outside this pass's enumerated scope and the opinion's explicit "do not pre-split"
  guidance -- **deferred, not pre-split**, to keep this pass's diff contained.
- **~20 single-line `_fn`/`_callable` unwrap-helper migrations** (Pass 4) --
  **CLOSED: deferred, mechanical/budget** (each saves ~2 LOC with per-file import
  churn; non-blocking, not a duplication-of-logic concern).
- **unit-vs-integration boundary leak** (registration tests in `unit/` that import
  the whole server) (Pass 4) -- **CLOSED: observation only**, no correctness issue;
  no reclassification this pass.
- **External-oracle coverage gaps** (composite blend-modes, masking/alpha renders,
  audio-loudnorm end-to-end) (Pass 4) -- **CLOSED: out of scope** -- these are
  *new test authoring*, not duplication/consistency consolidation.

**Files touched (src):** `pipelines/guides.py`, `pipelines/vo_loop.py`,
`pipelines/_common.py` (docstring), `production_brain/skills/voiceover.py`,
`server/tools/audio.py`, `server/tools_helpers/_workspace.py`. **(tests):**
`tests/integration/external/builders.py`, `tests/_testkit.py` (docstring).
**(docs):** `CLAUDE.md`. **Notes document appended; every listed carry-forward
closed with a verdict.**

---

## Consolidation-5 (2026-07-04) — final dead-weight sweep + coherence close (CLOSING SECTION)

Final sweep before real-world dogfooding. Bias: **removal + document-truth**, no
new construction. No commit made (working tree carries the sweep).

### Dead-weight removed (by class)

| Class | Detector | Count | Disposition |
|---|---|--:|---|
| Unused imports (F401) | `ruff --select F401` | **~715** | Auto-removed (`ruff --fix`, safe only). Dominated by the hardening-pass boilerplate **error-vocabulary block** in ~30 `server/bundles/*` (each imported the full `errors.py` constructor set; only `tool_guard`/`err`/`operation_failed`+used ones kept) plus the per-`tools/*` unused `_err`, stray stdlib/typing/model imports (`json`, `Path`, `yaml`, `Any`, `datetime`, `uuid`, `Field`, `list_profiles`, `MarkerConfig`, …). |
| Unused locals (F841, safe) | `ruff --select F841` | ~13 | Auto-removed (incl. `compositing_masking._exc`). |
| Unused locals (F841, side-effect RHS) | hand-review | **11 src** | Hand-fixed: pure-dead removed (`step_start_frame`, `min_topics`, `key`, `avg_likes`, `entry`, `fps`, `n_overlay`, `n_ch`, `materials`, `tools`, `description`); side-effecting calls kept as bare calls (`new_project.WorkspaceManager.create(...)`, `clips_nle._validate_clip_index(...)`). |
| Latent bug (F821 undefined name) | `ruff --select F821` | **1** | `app/cli.py` return annotation `"Path \| None"` referenced un-imported `Path` (harmless under `from __future__ import annotations`, but breaks `get_type_hints`). Fixed by adding module-level `from pathlib import Path`. |
| Leftover scratch / untracked strays | git status + `ls docs/research -R` | 0 removed | `docs/research/.../scratch/build_candidates.py` **KEPT** — it is a *cited* generator in the `kdenlive-gui-bin-rejection.md` findings (has PROVENANCE, reproducibility), not an untracked stray. All untracked items are `smoke-test/` + `transcripts/` **runtime output** (not repo scratch); left untouched. |

**Net LOC:** src 59,708 → **59,139** (−570 across 249 modules); tests 55,630 →
**55,503** (−127). `git diff --shortstat`: **177 files, +100 / −735**.

### Aliases removed vs kept-with-reason

- **Removed:** 0 delegate *aliases*. Passes 1-4 kept local delegate names
  ("where tests monkeypatch them"); grepping each candidate confirmed they are
  still live (unit/integration import or monkeypatch the local name), so **none
  were orphaned**. The F401 removals above are *unused imports*, not delegate
  aliases — verified: 0 test monkeypatches any removed error-constructor name on
  a bundle module, and the full suite (which imports the whole server) stays
  green, proving no cross-module re-export was severed.
- **Kept-with-reason:** `adapters/kdenlive/patcher.py` (the split-compat shim,
  ~38 F401) re-exports every public+private `patcher_intents`/`effect_stack` name
  by design (docstring-documented back-compat surface; `_iter_clip_filters` is
  actively monkeypatched by `test_stack_ops_*`). **Reverted `ruff --fix` on this
  file**; the 38 F401 are intentional and now called out in `CLAUDE.md` Testing.
  14 test-side `result = tool(...)` F841 kept (legitimate call-for-side-effect
  style; auto-strip is an unsafe fix that could drop the call).

### Docs updated

- **`CLAUDE.md`** — new **"MCP Tool Modules (auto-discovered)"** section (both
  `server/bundles/` and `server/tools/` are pkgutil-discovered; new tool = new
  file, zero shared-file edit); new **"Authoring a New MCP Tool" 7-step
  checklist** (logic-in-pipeline; drop-in module; `errors.py` contract +
  `tool_guard`; parse→validate→snapshot→mutate→serialize order; canonical helpers
  `_common`/`tools_helpers`-package/`patcher`/`probe`; `_testkit` + external
  render proof for timeline-affecting tools; vault guide note); Testing section
  now documents the `ruff --select F401,F841` dead-code check + the patcher-shim
  carve-out; layering line added.
- **`docs/ai-handoff.md`** — `server.py` row rewritten to describe the
  auto-discovery of `server/tools` + `server/bundles` (201 live tools) instead of
  the old "imports tools and resources modules".
- Authoring checklist durable home: **`CLAUDE.md`** ("Authoring a New MCP Tool").
  The external forge `plugin-authoring` skill is about Claude-Code plugin
  scaffolding generally (not this repo's MCP-tool conventions) and lives outside
  the repo — intentionally not the home for this checklist.

### Surface accounting — what the 10 passes bought

Baseline is Pass-1 start (`514f69d`). "10 passes" = 5 consistency (1562c97…922f86a)
+ 5 consolidation (b6db0fe…this).

| Metric | Pass-1 baseline (`514f69d`) | Consolidation-5 close | Δ |
|---|--:|--:|--:|
| Live MCP tools | 201 | **201** | 0 (surface intentionally frozen) |
| src LOC | ~60,900 | **59,139** | ≈ −1,760 |
| src modules | 243 | **249** | +6 (net: −? merged, +`tools_helpers/` 6-module package split) |
| tests LOC | (n/a tracked p1) | **55,503** | — |
| test files | — | **228** | — |
| tests collected | 4,205 | **4,205** | +2 net over the run (regression tests added, dedup removed) |
| suite result | 4,203 pass / 1 skip | **4,204 pass / 1 skip** | 0 fail |
| F-level dead code (F401/F841 excl. intentional patcher shim + test side-effect locals) | not measured | **0** | drained |

The value: ~1.2k LOC of *duplication* drained (consistency 1), API/units made
canonical (2), model→pipeline→shell layering enforced with logic pushed out of
the shell (3), test-suite deduped onto a shared `_testkit` + flake root-caused (4),
`tools_helpers` split into a domain package + `tools/` auto-discovery retiring the
last shared-file contention point (consolidations 1-2), ADR-005 boundary codified
(3), carry-forwards all closed (4), and this pass drained the residual dead
imports/locals + fixed one latent `F821`. Tool surface held at **201** throughout.

### Final verification battery (line by line)

- Full suite run 1 (`uv run pytest tests/ -q`): **4204 passed, 1 skipped**, 0 fail, 155.35s.
- Full suite run 2 (`uv run pytest tests/ -q`): **4204 passed, 1 skipped**, 0 fail, 154.64s.
- External tier isolated (`pytest tests/integration/external/ -q`): **61 passed, 1 skipped**, 30.20s.
- `-m external` partition: **60 collected**; `-m "not external"`: **4145**; 60 + 4145 = 4205 = full collection (clean, no overlap/gap).
- Live tool count (`registered_tool_names()`): **201**.
- CLI smoke (`import workshop_video_brain.app.cli`): **OK** (also `import ...server` OK).
- Zero-edit drop-in proof: temp `@mcp.tool()` module dropped into **both** `bundles/` and `tools/` → registry **203** (201+2), **both probes registered**; modules removed → back to **201**, no strays.
- Boundary tests (`tests/unit/test_module_boundaries.py`): **4 passed**.
- `ruff check --select F401,F841` final: **38 F401 (all patcher shim) + 14 F841 (all test-side call-for-side-effect)** — no other F-level dead code. Full default ruleset residual (NOT chased, style-only): E402×82 (deliberate lazy/escape-hatch imports), F541×10, E741×8, E702×4 — no F811/F821/F823.

**Notes document complete. This is the CLOSING section — no further appends.
Consolidation mandate closed; project proceeds to dogfooding.**
