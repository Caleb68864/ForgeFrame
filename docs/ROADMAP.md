---
date: 2026-11-16
topic: "ForgeFrame roadmap (current)"
status: active
supersedes-status-of:
  - docs/plans/2026-04-08-feature-roadmap.md
  - docs/plans/2026-04-08-roadmap-phase2-design.md
  - docs/specs/2026-04-08-roadmap-phase2.md
---

# ForgeFrame roadmap

This is the current roadmap. The April documents above stay as history; this
file says what in them is done and what is next. Every status below was
checked against the code on 2026-11-16 (branch `work/audit-wip-and-roadmap`,
from `main` at `f4ff03f`), not copied from earlier status notes.

Today: 21 `ff-` skills, 233 registered MCP tools (counted from the live
registry), 5,100+ tests. The "Current Stats" block in the April roadmap
(16 skills, 73 tools, 1,242 tests) is out of date.

Legend: **Done** / **Partly** / **Not started** / **Blocked** (needs the owner or an
upstream release).

## 1. What's next, ranked

Ranked by user harm first, then effort. Items 1, 2 and 4 are defects in
shipped behaviour, so they come before new features.

| # | Item | Why it ranks here | Where | Size |
|---|---|---|---|---|
| 1 | **Done 2026-11-16** (branch `fix/kdenlive26-import-and-selects`): `parser.mlt_time_to_frames` reads frame counts, clock timecode and SMPTE (incl. drop-frame) at the profile frame rate; proof `tests/unit/test_parser_timecode.py` (Kdenlive 26.08.2-written fixture `tests/fixtures/projects/real/timecode_2608.kdenlive`) and `test_kdenlive_differential.py::test_kdenlive_rewrite_imports_same_timeline`. `corpus_clip_ids_2604` now round-trips. Was: **The parser drops the timeline of a native Kdenlive 26.x save.** Native saves write `in`/`out` as timecode (`in="00:00:00.000"`); `parser.py` calls `int()` on them, logs "Skipping malformed <playlist>", and the playlist and its entries are gone. Reproduced 2026-11-16: a two-element project parsed to 0 playlists. | Opening or importing a project the user saved in Kdenlive (the version they actually edit with) loses its timeline. Known since 2026-11-02, never scheduled. | `edit_mcp/adapters/kdenlive/parser.py` (~L490, L624-672) | S-M |
| 2 | **Done 2026-11-16** (branch `fix/kdenlive26-import-and-selects`): out-point is `seconds_to_frames(end) - 1` and guides sit at the running timeline frame; the same off-by-one in `assembly.assemble_timeline` (primary and insert out-points) is fixed too. Proof `tests/unit/test_selects_timeline.py::TestSelectsTimelineFrameAccuracy`, `tests/unit/test_assembly.py::TestAssembleTimelineFrameAccuracy`, melt render `tests/integration/external/test_selects_timeline_render.py` (52 -> 50 frames). `replay_generator.generate_replay` had the same out-point; fixed 2026-11-16 (branch `fix/qc-replay-vfr`), proof melt render `tests/integration/external/test_replay_render.py` (252 -> 250 frames). Found then, fixed 2026-11-16 (branch `fix/replay-crossfade`): the replay's crossfade was a raw `<transition>` with no `mlt_service`, so melt logged `failed to load transition "(null)"` and the reel had hard cuts. It now goes through `patcher_intents._apply_add_transition` (the `transitions_apply` path: incoming segment on a new top track, 24-frame `luma`/`dissolve` overlap; segment guides follow the pull-in), so the reel is 24 frames shorter per crossfade (250 -> 226). Proof `tests/integration/external/test_replay_render.py` (melt load check re-enabled; red/blue sources, mid-overlap frame is a blend of both). Not yet: the replay producers carry no `length`, so the overlap never uses source handles. Was: **`build_selects_timeline` out-points and guides are off.** Out is `seconds_to_frames(end)` (one frame long per clip; the jump-cut builder in the same file uses `- 1`), and each guide sits at the clip's *source* `in_point`, not its timeline position, so guides are wrong whenever selects are not source-ordered. | Feeds `timeline_build_selects`, the guided workflow and assembly, i.e. every first cut. | `edit_mcp/pipelines/selects_timeline.py` L179-199 (vs. L235-268) | S |
| 3 | **Prompt 06: GUI pass, then rewrite the CLAUDE.md "Hard rules" to the 26.x contract.** The target was decided as Kdenlive 26.x on 2026-10-13, the serializer emits the 26.04 E shape, but `CLAUDE.md` still says "target Kdenlive 25.x" and hard rule 2 still mandates 25.x twin chains. Agents reading CLAUDE.md are told the wrong contract. | **Blocked on Caleb** for Part A (open the check pack in the Kdenlive GUI and record any dialogs). Part B (the rewrite) follows. | `docs/prompts/06-gui-pass-and-hard-rules.md`, `CLAUDE.md` | S (after GUI) |
| 4 | **Done 2026-11-16** (branch `fix/kdenlive26-import-and-selects`): doctor builds the default (CSRT) tracker through `motion_track.opencv_tracker_status` (same constructor path as the engine) and reports it under `motion_track`; checked against real opencv 5.0.0 wheels (headless: not ready, contrib: ready). Proof `tests/unit/test_discovery_commands.py::test_motion_track_*`. Was: **`wvb doctor` reports `motion_track_python` ready when no tracker exists.** It checks only that `cv2` imports; `opencv-python-headless` has no CSRT/KCF trackers without contrib, so the tool fails after doctor said yes. | A readiness check that lies. Tiny fix: probe the tracker constructors the pipeline actually uses. | `app/doctor.py` L62, L95; `edit_mcp/pipelines/motion_track.py` ~L573 | XS |
| 5 | **Done 2026-11-16** (branch `fix/qc-replay-vfr`): silence fails only on a run > 2 s, > 50 % of the duration silent, or > 1 s at the very start/end (every pause still listed); loudness is checked against a configurable target, default -14 LUFS +/-4 LU (the guide's -18..-10 window), reporting the distance and failing over-loud masters; new `profile` check against a render profile (`profile=`) or the workspace project (`workspace_path=`). Decision: `docs/decisions.md` 2026-11-16. Proof `tests/unit/test_qc_check.py`, `tests/integration/test_qc_check_real_ffmpeg.py`. Was: **QC false failures and missing checks.** `_check_silence` fails a render on any single 1 s gap under -50 dB (normal pauses in a tutorial); `_check_loudness` only fails below -24 LUFS and never reports distance from -14 LUFS or flags an over-loud master; `qc_check` is not profile-aware (resolution/fps/codec). | `qc_check` is the last gate before publishing; a check that fails good renders gets ignored. | `edit_mcp/pipelines/qc_check.py` L145-182; `server/tools/render.py::qc_check` | S |
| 6 | **Done.** (c) done 2026-11-21 (branch `feat/vfr-single-file`): `media_check_vfr(workspace_path="", file_path="")` checks one file through new `vfr_check.check_vfr_file` (no workspace needed, so a recording can be checked before ingest; a relative `file_path` reads against `workspace_path`), same report shape and `all_cfr` rule as the scan, `_cfr` copy still resolves it, a file with no video stream is `unprobed` rather than CFR. The scan and the single-file check share `_classify_vfr`. Handbook Ch.14 called `media_check_vfr file=...` and `media_transcode_cfr file=... fps=... output=...`, neither of which existed; both examples now use the real parameters. Proof `tests/integration/test_vfr_single_file.py` (real ffmpeg/ffprobe). (a) and (b) done 2026-11-16 (branch `fix/qc-replay-vfr`): `probe.frame_rate_divergence` (`|r-avg|/max(r,avg)`) and `VFR_DIVERGENCE_THRESHOLD` are the one rule for both `is_vfr` and the reported `divergence_pct`; a VFR original whose `_cfr` sibling exists and probes CFR is listed in `resolved_files` and no longer blocks `all_cfr`. Proof `tests/unit/test_vfr_check.py::TestDivergenceFormula`, `::TestConvertedOriginals`. Was: **VFR follow-ups.** (a) `probe.py` decides `is_vfr` with `|r-avg|/max(r,avg)`, the report shows `|r-avg|/avg`; use one helper. (b) After `media_transcode_cfr`, the VFR original stays in `media/raw/` beside its `_cfr` copy, so `media_check_vfr` keeps reporting it and `all_cfr` can never become true. Recognise a file whose `_cfr` sibling exists. (c) No single-file check. | Small, and (b) makes the tool's own success flag unreachable after the user follows its advice. | `adapters/ffmpeg/probe.py`, `pipelines/vfr_check.py` | S |
| 7 | **Done 2026-11-16** (branch `feat/capture-prep-entry`): MCP tool `capture_prep_checklist(workspace_path, target_resolution, target_fps)` (`server/bundles/capture_prep.py`) and `wvb plan capture-prep WORKSPACE_PATH [--target-resolution] [--target-fps] [--json]`, both thin shells over `capture_prep.load_shot_plan` + `capture_prep_payload`, so the generator's own validation is the only check. Read-only: no shot plan gives a generic checklist plus a `note`. Skill, skill reference, user workflow and `docs/capabilities.md` updated. Proof `tests/unit/test_capture_prep_entry.py`. Still open (owner): whether `target_fps` should accept 23.976/29.97; it stays whole-number only. Was: **Capture prep has no tool or CLI entry point.** Only the skill's inline Python called `generate_capture_checklist`. | The Reliability rule: "available through documented user entry points". | `production_brain/skills/capture_prep.py`, `skills/ff-capture-prep/SKILL.md` | S |
| 8 | **Prompt 17 done 2026-11-21** (branch `feat/undo-journal`): `project_undo` / `project_redo` / `project_history` / `timeline_batch` on a per-workspace journal (`workspace/undo.py`, fed by `serialize_project` + `snapshot.restore`, grouped per call by `tool_guard`); a failed batch rolls back by depth and leaves the working copies byte-identical. Proof `tests/unit/test_undo_journal.py`, `tests/unit/test_timeline_batch.py`; decision `docs/decisions.md` 2026-11-21; note `vault/wiki/forgeframe-undo-journal.md`. **Prompt 18 done 2026-11-22** (branch `fix/headless-melt-display`): melt renders stream `-progress2` stderr into `on_progress` (jobs record `progress.percent`/`engine`, throttled), 100 % only after verification; `verify_render_output` now also requires a video stream, an audio stream when the profile has audio, and no shorter than the timeline (`Render is shorter than the timeline: ...`). Proof `tests/unit/test_melt_progress.py`, external `tests/integration/external/test_melt_progress_render.py` (both fail on the old code). Decided by agent 2026-11-22 (owner may revisit): the render streams through `Popen` only when a progress callback is given; without one it keeps the single `subprocess.run`. **Prompt 19 done 2026-11-22**: `effect_list_applied`, `effect_param_get`, `effect_param_set`, `effect_toggle`, `effect_remove` (`server/bundles/effect_edit.py`, intents `SetEffectParams` / `SetEffectEnabled` / `RemoveEffect`); a bypassed effect is `disable=1` in the file and renders as no effect in melt. Proof `tests/unit/test_effect_edit.py`, external `tests/integration/external/test_effect_edit_render.py`. Kdenlive-vs-melt render of a disabled effect not checked (no `requires_kdenlive` mark). **Prompt 20 done 2026-11-22** (branch `feat/trim-tools`): `clip_slip`, `clip_slide`, `clip_replace`, `clip_ripple_insert` over intents `SlipClip` / `SlideClip` / `ReplaceClip` / `RippleInsert` (`adapters/kdenlive/patcher_trims.py`, planner `pipelines/trim_ops.py`); each moves the linked audio entry with the clip or is skipped whole, raises producer `length` per rule 14, refuses timewarp clips. Proof `tests/unit/test_trim_ops.py`, `tests/unit/test_clip_trims_tools.py`, external `tests/integration/external/test_trim_tools_render.py`. Known gaps (not changed, per the prompt): `PlaceClip` insert puts a blank on the audio track, does not shift transitions, and drops the right half's filters when it splits a clip on another track; `TrimClip`, `InsertGap`, `RemoveClip`, `MoveClip`, `SplitClip` and `RippleDelete` still change only the named playlist (no linked audio). Slide does not adjust neighbours' entry-local keyframes. **Prompt 21 done 2026-11-22**: easing maths + `bake_keyframes` (`pipelines/easing.py`), `bake`/`bake_step` on `effect_keyframe_set_scalar/rect/color` (native output unchanged when off; `cubic_bezier`/`spring`/inline amounts need `bake=true`), `effect_camera_move` with `zoom_punch` / `orbit` / `handheld` (`pipelines/camera_moves.py`). Real melt: a cubic-in box at frame 10 has its red centroid at 69.6 px native and 69.6 px baked vs 159.5 px linear. Still for the owner: open `kdenlive-check-pack/21_easing_native.kdenlive` and `21_easing_baked.kdenlive` (from `scripts/kdenlive_check_pack.py`) in Kdenlive 26.08 and note whether the keyframe panel keeps the native operator. **Prompt 22 done 2026-11-22**: `snapshot_diff(a="previous", b="latest")` compares parsed versions (working copies, snapshot ids, workspace paths) and reports tracks, clips (aligned, so an insert is one added clip), clip effects, track filters, transitions (frames or timecode), guides, bin and duration as JSON plus sentences. Read-only; proof `tests/unit/test_project_diff.py`, `tests/unit/test_snapshot_diff_tool.py`. Next: 23. **Expansion Phase 4: prompts 17-24** (undo/redo + `timeline_batch`, melt `percentage:` progress, applied-effect editing, trim tools, easing/camera moves, `snapshot_diff`, beat sync, chain-per-placement experiment). | First new-feature work. Do in prompt order; 19, 21, 23 must use the effect-id resolver. | `docs/prompts/17-*.md` .. `24-*.md` | M-L each |
| 9 | **Expansion Phase 5: prompts 30-39** (bare-file media layer: trim, concat, reframe, speed, gif, convert, audio files, `transcribe_file`, subtitle ops, text-based editing, image tools). | Grows ForgeFrame from a Kdenlive editor into a general media MCP. Depends on 30 first. | `docs/prompts/30-*.md` .. `39-*.md` | M-L each |
| 10 | **Prompt 07: `kdenlive --verify-file` as a validator backend.** | **Blocked** until a Kdenlive release ships the flag (26.08.2 does not; checked 2026-11-02). | `docs/prompts/07-verify-file-validator.md` | S |
| 11 | **Done 2026-11-16** (branch `feat/reaction-gif`): captioned reaction GIFs, rebuilt from the owner's vault `make_gif.py` (find -> scene -> gif). Pipeline `edit_mcp/pipelines/reaction_gif.py` (SRT search with 4 context cues and the ~3 s subtitle-ahead-of-picture window, contact sheet, `showinfo` shot cuts, waveform, 15 fps / 480 px lanczos render with a `textfile=` caption sized from width, two-pass bayer palette, check strip, GIF gallery `$WVB_GIF_GALLERY` or `~/Pictures/Reaction GIFs`) and thin yt-dlp wrappers `adapters/youtube/ytdlp_cli.py`. Proof `tests/unit/test_reaction_gif.py`, real-ffmpeg `tests/integration/test_reaction_gif_render.py` (ends 0.04 s before a hard cut with no second-shot frames). MCP tools `gif_find_line(source, text, context=4, picture_offset=3.0, work_dir="")`, `gif_fetch_scene(source, start="", end="", out_dir="", contact_sheet=True, fine_sheet_at="", waveform_at="")`, `gif_render(clip_path, start, end, caption="", output_path="", gallery_dir="", width=480, fps=15)` (`server/bundles/reaction_gif.py`) and `wvb gif find|scene|render`; skill `ff-reaction-gif` (evidence-first rules), skill reference, user workflow, README and `docs/capabilities.md` updated. Not done: no live Tubi/YouTube run (no downloads during development), so the yt-dlp wrappers are proven only by command-shape tests. | Owner workflow note; no tool for it existed. | `edit_mcp/pipelines/reaction_gif.py` | S-M |

Found and fixed 2026-11-21 (branch `feat/undo-journal`): in a headless local
shell the external tier failed `test_image_overlay_render.py` (3) and
`test_pan_zoom_render.py::test_transition_rect_zoom_moves_pixels` -- the
oracle's `render_frame` / `render_video` / `melt_accepts` ran melt without a
display, so Qt producers (`qimage`, `qtblend`) rendered a flat grey frame. Only
`melt_render_full` had the `xvfb-run` fallback (the title fix, PR #14); all four
now go through `_oracle.with_display`. External tier headless: 117 passed, 1
skipped. `tests/integration/test_title_renders.py` had the same gap plus no
`terminate_on_pause=1` and no timeout: headless, its melt ran 17+ minutes until
killed. It now uses the shared `tests/_testkit.with_display`, `terminate_on_pause=1`
and `timeout=180`. Product side, fixed 2026-11-22 (branch `fix/headless-melt-display`):
ForgeFrame's own melt / MLT-bindings subprocesses (render executor, load check,
timeline frame grab, MLT worker, subtitle burn-in) ran with no display check, so
headless they drew titles as "INVALID" and still reported success. They now run
with `QT_QPA_PLATFORM=offscreen` when there is no display
(`adapters/mlt/display.py`; on melt 7.42 pixel-identical to `xvfb-run`), any
output still carrying MLT's "requires a X11 or Wayland environment" fails the
render (`missing_dependency`), and `wvb doctor` reports `mlt_qt` /
`timeline_render_qt` from a real one-frame `qtext` probe. Proof
`tests/integration/test_headless_qt_render.py` (4 of 5 fail on the old code).
Found on the way: `test_timeline_thumbnails.py::test_title_composite_matches_the_slow_melt_method`
compared two headless "INVALID" frames and passed; its reference melt now gets a
display. Decided by agent 2026-11-22 (owner may revisit): Qt offscreen instead
of wrapping melt in `xvfb-run` -- no extra package, and a timeout kill does not
orphan melt and Xvfb behind the `xvfb-run` shell script.

Found and fixed 2026-11-22: `effect_add` with JSON numbers or booleans in
`params` -- its own docstring example `{"opacity": 0.5}` -- failed `AddEffect`
validation (`dict[str, str]`) and came back as an "unexpected error". Values are
now stringified (`true` -> `1`). Proof `tests/unit/test_effect_add_numeric_params.py`.

Found and fixed 2026-11-22: `latest_project` picked between two files at the
same `_vN` (e.g. `project_v1` and `my-slug_v1`) by directory-listing order, which
differs between filesystems -- the cause of PR #16's CI-only failure. Ties now go
to the newer file, then the name. Proof `tests/unit/test_latest_project.py::TestLatestProjectTies`.

Found and fixed 2026-11-22: `test_timeline_thumbnails.py::test_melt_fallback_grabs_the_composite`
failed intermittently in full runs ("melt could not grab frame 45:" with nothing
after the colon, once a 600 s timeout). Cause, measured with the same one-frame
melt command: under CPU contention melt 7.42 sometimes exits 0 without writing the
frame, or stalls after loading its plugins (0 of 120 sequential grabs; 2-7 of
128-160 with 16 grabs in parallel), and `_melt_frame` reported both as an
unexplained error. Each grab attempt now has a 60 s ceiling and an empty or stalled
attempt is retried (3 attempts); a real melt error (non-zero exit with a message) is
not retried; the error names every attempt's exit code and stderr. 192 grabs at
16-way concurrency: 0 failures, 9 needed a retry. The cause inside melt itself is
not identified. Proof `tests/unit/test_melt_frame_retry.py`.

Found and fixed 2026-11-22: `test_faults_adapter.py::test_large_project_parse_serialize_bounds`
failed under load because it used absolute seconds, and the slowness it tolerated
was a defect: `serializer._effective_length` scanned every playlist entry for every
producer, so serializing was quadratic (10 000 clips 9-14 s; 4x the clips cost 11.5x
the time). One pass now collects each producer's largest out-point (10 000 clips
~4 s; ratio ~6). The test now asserts the 2 500 -> 10 000 clip time ratio (< 8.5,
best of two, interleaved), which load cannot fail and the old code does; memory and
round-trip fidelity are a separate test.

Also outstanding, not ranked as work: detached jobs are POSIX only; job progress
is per frame for renders (melt `-progress2`, prompt 18, 2026-11-22), per stage otherwise;
other move/trim intents are still known A/V sync gaps (feature roadmap,
Kdenlive step 2). Owner decisions still open from 2026-11-02: frame-rate
override and default engine.

## 2. `docs/plans/2026-04-08-feature-roadmap.md`, item by item

### Phase 1 and Phase 2 lists ("What's Built")

| Item | Status | Proof |
|---|---|---|
| Phase 1 (transcripts, auto-marking, chapters, Obsidian notes, review/selects timelines, Kdenlive adapter, transitions + render, CLI) | Done | `48d7ce6` (v1); tools `transcript_generate`, `markers_auto_generate`, `timeline_build_review`, `timeline_build_selects`, `transitions_apply`, `render_preview` in the registry |
| Phase 2 skills (broll-whisperer, pacing-meter, pattern-brain, voiceover-fixer, auto-editor, audio-cleanup, publish, social-clips, youtube-analytics) | Done | `workshop-video-brain/skills/ff-*/SKILL.md` (all nine present) |
| Build Replay, Title Cards, B-Roll Library | Done | `replay_generate`, `title_cards_generate`, `broll_library_*` tools (`404c2c6`) |

### Phase 3: High Impact / Low Effort

| # | Item | Status | Proof |
|---|---|---|---|
| 1 | Capture Prep skill | Done; entry point done (next #7); 23.976/29.97 still an owner decision | `43b02c5`; hardened `f4ff03f` (input validation, VFR advice); `tests/unit/test_capture_prep.py` |
| 2 | VFR detection (`media_check_vfr`, `media_transcode_cfr`) | Done; follow-ups (next #6) done | `43b02c5`; `e92e81b` fixed 0/1 rates and false `all_cfr`; `-fps_mode` fix FF1 (PR #1); `tests/integration/test_vfr_check_real_ffprobe.py` |
| 3 | Full render (`render_final_tool`, five presets) | Done | `43b02c5`; profiles shipped in the wheel FG4 (`97a8fcf`); `5d45713` stopped it picking a stale snapshot; `tests/unit/test_render_final_project_selection.py`, `tests/unit/test_render_final_tool_errors.py` |
| 4 | QC automation (`qc_check`) | Done; follow-ups next #5 | `43b02c5`; hardened `97a82d3`; `tests/integration/test_qc_check_real_ffmpeg.py` |

The April file says item 1-4 were "verified against the code on branch
`wip/2026-11-09-phase3`". No such branch exists locally or on `origin`; the
work landed directly on `main` as `97a82d3`, `e92e81b`, `5d45713`, `f4ff03f`.

### Phase 3: Medium Effort and Longer Term

All five were implemented in the same April commit and were never marked done.

| # | Item | Status | Proof |
|---|---|---|---|
| 5 | Color analysis + LUT (`color_analyze`, `color_apply_lut`) | Done | `43b02c5`; both tools registered; missing LUT files are refused before render (FG3, `cbe6413`) |
| 6 | Effects application (`effect_add`) | Done | `43b02c5`; Kdenlive effect identity (`kdenlive_id`) enforced `da08b49`, render-verified 2026-11-02 |
| 7 | Project profile setup (`project_setup_profile`) | Done | `43b02c5`; tool registered |
| 8 | Compositing (`composite_pip`, `composite_wipe`) | Done | `43b02c5`; also `composite_set`, `composite_split_screen` |
| 9 | Project archive (`project_archive`) | Done | `43b02c5`; tool registered |

### Next Step: Kdenlive 26.08 compatibility

| # | Item | Status | Proof |
|---|---|---|---|
| 1 | Automate the differential | Done | `5724bb7`; `tests/integration/external/test_kdenlive_differential.py`, 21 cases |
| 2 | Audio lost on insert | Done (other move/trim intents still sync gaps) | `5724bb7`, `7025f60` (`kdenlive:audio_track=1`) |
| 3 | Effects dropped by Kdenlive | Done | `da08b49`; `effect_identity.normalize_effect_id` |
| 4 | Dissolves dropped | Done | `38fe0e1` |
| 5 | Hard-rule violations in generated XML | Done | `da08b49`; `test_bin_lengths.py`, `test_serializer_entry_ids.py`, `test_speed_variant_bin.py` |
| 6 | GUI pass + hard rules rewrite | Blocked on owner (next #3) | `CLAUDE.md` still says "target Kdenlive 25.x" |
| 7 | `kdenlive --verify-file` | Blocked upstream (next #10) | |
| 8 | `test_frames_match[title]` fails locally (PSNR 16.21 dB) | Done 2026-11-16 (branch `fix/title-differential`) | Not a serializer bug: our title producer XML matches what Kdenlive 26.08.2 rewrites. The melt side (`_oracle.melt_render_full`) ran without a display, so melt 7.42's Qt module refused to load `kdenlivetitle` and drew "INVALID" over the frame; `kdenlive_render` already used `xvfb-run`, and CI hid it by running the whole suite under `xvfb-run`. `melt_render_full` now wraps in `xvfb-run -a` when neither `DISPLAY` nor `WAYLAND_DISPLAY` is set; title PSNR 43.19 dB, threshold unchanged at 33. |

The section's "done when" (GUI pass shows no dialogs) is therefore not met.

### Reliability and Guided Workflow

| # | Item | Status | Proof |
|---|---|---|---|
| 1 | Unify preview and final rendering | Done | `pipelines/render_pipeline.run_render`; `docs/testing/2026-11-02-reliability-runtime-validation.md` |
| 2 | Validate serialized XML | Done; 25.x vs 26.x contract still open (next #3) | `adapters/kdenlive/validator.py`; FG2 (`00be45e`) |
| 3 | Persistent jobs | Done (POSIX only) | `workspace/jobs.py`, `job_*` tools, `tests/integration/test_reliability_cli.py` |
| 4 | Central safe file writes | Done | `workspace/safe_write.py`, `tests/unit/test_protected_paths.py` |
| 5 | Capability discovery (`wvb doctor`) | Done; false-ready motion-track row fixed 2026-11-16 (next #4) | `app/doctor.py`, `docs/capabilities.md` |
| 6 | Guided project workflow | Done; selects bug fixed 2026-11-16 (next #2) | `wvb workflow`, `workflow_start`, `pipelines/guided_workflow.py` |

### Open follow-ups found 2026-11-09

| Item | Status | Where it went |
|---|---|---|
| QC silence threshold | Done 2026-11-16 | next #5 |
| QC loudness only "too quiet" | Done 2026-11-16 | next #5 |
| QC not profile-aware | Done 2026-11-16 | next #5 |
| Capture prep entry point | Done (`capture_prep_checklist`, `wvb plan capture-prep`) | next #7 |
| Two VFR divergence formulas | Done 2026-11-16 | next #6 |
| Single-file VFR check | Done 2026-11-21 (`media_check_vfr(file_path=...)`) | next #6 |

### Skip For Now

Tool-aware editing (CV), experiment engine, multi-editor/OTIO, speaker
diarization: still skipped. Nothing has changed the reasons.

## 3. `docs/plans/2026-04-08-roadmap-phase2-design.md` and `docs/specs/2026-04-08-roadmap-phase2.md`

All five features landed in `404c2c6` ("Roadmap Phase 2"). Checked per
sub-spec against the acceptance criteria:

| Sub-spec | Status | Proof |
|---|---|---|
| 1 B-Roll Whisperer | Done | `pipelines/broll_suggestions.py`; tool `broll_suggest`; `wvb broll suggest` (`app/cli.py` ~L1221); skill `ff-broll-whisperer`; Obsidian section `broll-suggestions` (`production_brain/skills/broll.py` L78) |
| 2 Pacing Meter | Done | `pipelines/pacing_analyzer.py` (100/160 WPM thresholds L13-14, weak-intro rule L192); `pacing_analyze`; `wvb pacing analyze`; skill `ff-pacing-meter` |
| 3 Build Replay | Done | `pipelines/replay_generator.py` (2 s padding, merge, 24-frame `luma` crossfade via `_apply_add_transition`); `replay_generate`; `wvb replay generate` |
| 4 Pattern Brain | Done | `pipelines/pattern_brain.py`; `pattern_extract` saves `reports/build_notes.md` (`server/tools/assembly_titles.py` ~L246); `wvb pattern extract`; skill `ff-pattern-brain` |
| 5 Title Cards | Done | `pipelines/title_cards.py` (`TITLE:` guides ~L136); `title_cards_generate` writes `reports/title_cards.json`; `wvb title-cards generate` |

The spec's verification step 3 ("open generated Kdenlive projects ... both
load correctly") is part of the prompt 06 GUI pass (next #3).

## 4. Other plans this roadmap absorbs

`docs/plans/2026-10-13-media-mcp-expansion.md`: Phases 0-3 done (2026-11-02,
prompts 10-16, merged in `9b65bd3`); Phase 4 = next #8; Phase 5 = next #9 (its
one done item, source-profile selects/assembly builders, landed in `7025f60`).
`docs/prompts/00-README.md` keeps the per-prompt status table.

## How to keep this current

When an item lands, mark it here in the same commit, with the commit or test
that proves it. Re-rank section 1 when a defect is found.
