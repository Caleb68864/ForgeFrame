# Hardening Pass 3a — composed-workflow failure propagation

Scope owned: **new tests** (`tests/integration/test_workflow_failures.py`) and
**propagation/behavior fixes anywhere in `src`**. Passes 1–2 hardened individual
tools; this pass asks whether a mid-pipeline fault surfaces *comprehensibly*
downstream, or cascades into a baffling `operation_failed`/`KeyError`-grade
message — and whether any downstream step half-mutates before discovering the
upstream fault.

Method: 7 realistic multi-tool workflow scenarios built as permanent tests. Each
runs steps `1..k` for real, injects one fault, then drives steps `k+1..n` and
asserts each downstream tool (a) returns the right `error_type`, (b) names the
missing/corrupt upstream artifact, (c) points at the failed step via
`suggestion`, and (d) leaves the project byte-identical with no leaked snapshot /
no orphan temp dir on the way to the error.

ffmpeg + melt + ffprobe are all present in this environment, so the gated tests
**executed** here (not skipped). rembg / faster-whisper are absent (relevant to
scenarios 1 & 5). All melt invocations in the new suite are **bounded** (explicit
`timeout_seconds`) — a discovery run proved that `melt` on a project whose
producers reference missing media *hangs* until the 1800 s default; the new
tests never rely on that default.

## Test file

`tests/integration/test_workflow_failures.py` — **20 tests**, 7 scenario classes.
Full suite target: baseline `4159 passed, 1 skipped`.

---

## Scenario matrix: fault → per-downstream-tool verdict → fix

### 1. Media moved/deleted after ingest
| downstream tool | verdict | note |
|---|---|---|
| `clip_insert` | ✅ `missing_file`, names the path | already correct (Pass-2) |
| `media_thumbnail_sheet` | ✅ `missing_file`, names the path | already correct |
| `clip_place` | ❌→✅ **FIXED** | silently placed a broken clip (out_seconds given) or bailed with a confusing "duration unknown" message; now `missing_file` naming the media, before any snapshot/write |
| `transcript_generate` | ✅ documented limitation | workspace-scoped (ingests `media/raw`), takes no media arg, so it cannot *name* one file; asserted it never *fabricates* a transcript for a deleted asset |
| render (`execute_render`, melt) | ✅ not `succeeded`, no partial output | melt against missing footage does not report success; partial output removed (see §3 fix) |

### 2. Project corrupted mid-workflow  — **the money test**
Build via `clip_place` (×2) → truncate the `.kdenlive` bytes → downstream tools.
| downstream tool | verdict | note |
|---|---|---|
| `effect_add` | ✅ `corrupt_project`, names file | already correct |
| `composite_set` | ✅ `corrupt_project`, names file | already correct |
| `effect_color_grade` | ❌→✅ **FIXED** | unguarded `parse_project` → `operation_failed`; now `corrupt_project` |
| `clip_place` / `clip_move_to` / `clip_place_matched` | ❌→✅ **FIXED** | `_load` caught only `(ValueError, FileNotFoundError)`; `ProjectParseError` escaped to `tool_guard` → `operation_failed` ("report it"). Now → `corrupt_project` ("restore a snapshot") |
| `color_apply_lut`, `effect_color_wash`, `effect_scifi_greenscreen`, paper-cutout transition | ❌→✅ **FIXED** | these **snapshotted BEFORE parsing**: a corrupt project both mis-reported `operation_failed` AND *leaked a snapshot of the untouched file*. Reordered to parse→validate→snapshot→serialize; corrupt project now leaves **zero** side effects |

**Recovery (end-to-end, proven):** `snapshot_restore(good_snapshot)` restores the
project, the reparse succeeds, **the restored project still contains the real
`clip_place` work** (clip on track 0), and the **next `effect_add` SUCCEEDS** and
yields a valid re-parseable project. Money-test verdict: **PASS** — the full
corrupt → restore → succeed loop works, and recovery is of actual work, not just
"a parseable file".

### 3. Interrupted render
| assertion | verdict | note |
|---|---|---|
| timeout → job status | ✅ `failed`, never `succeeded` | already correct |
| partial output | ❌→✅ **FIXED** | a killed/timed-out melt left a half-written output file at `output_path` for a downstream `qc_check`/re-render/publish to mistake for a finished render. `execute_render` now records whether the output pre-existed and **discards a newly-created partial** on any failure/timeout/error path (`_discard_partial_output`), never touching a pre-existing file |
| `render_status` (MCP) | ✅ never reports a failed job as `succeeded` | registry-backed listing |
| re-render | ✅ succeeds, output present | |

### 4. Proxy divergence
| downstream tool | verdict | note |
|---|---|---|
| `proxy_status` after proxy deleted | ✅ `missing_proxy_count==1`, per-producer `missing_proxy_file=True` | already correct |
| render with proxy missing | ✅ `succeeded` via originals-swap | `originals_render_copy` swaps producer `resource` back to the original; bounded-timeout `execute_render` renders the real source and succeeds |

### 5. Missing dependency mid-chain (`mask_generate_and_apply`)
| assertion | verdict | note |
|---|---|---|
| engine absent at entry | ✅ `missing_dependency`, suggestion names the install | resolves *before* any frame extraction/snapshot |
| project state | ✅ byte-unchanged, **no snapshot taken** | matte generation precedes the snapshot; failure returns before it |
| temp dirs | ✅ no orphan `ai_mask_*` dirs | `TemporaryDirectory` cleans even on early return |
| engine fails **after** frames extracted (ffmpeg-gated) | ✅ error, no orphan temp dir, project untouched | injected a `MaskEngine` that raises mid-segmentation |

No fix needed — the engine-availability guard already sits ahead of all side
effects; this pass pins it with adversarial tests.

### 6. Stale transcript index — behavior **pinned loudly**
Intended behavior chosen and documented in the `transcript_search` docstring
("STALENESS CONTRACT"):
| tool | verdict | pinned behavior |
|---|---|---|
| `transcript_search` after a transcript JSON deleted (no reindex) | ✅ **returns the stale hit** | the FTS index is a derived cache; search auto-builds only when the DB is *missing*, and does not reconcile per-query. Documented + asserted (a test guards the contract: if search ever stops returning the stale hit, the docstring + test must change together) |
| `transcript_index_build` (incremental, no rebuild) | ✅ prunes the disappeared clip | search then returns clean |
| `shots_map_to_script` | ✅ **self-heals — no stale candidate** | it calls `build_index(rebuild=False)` first, so a deleted transcript is pruned before search; it never surfaces a stale clip |

No code fix beyond the docstring: the staleness is an intentional
cache/source-of-truth split, and the one consumer that must not act on stale hits
(`shots_map_to_script`) already reconciles first.

### 7. Chained assembly — multicam TOCTOU
| assertion | verdict | note |
|---|---|---|
| source deleted *before* `multicam_assemble` (cross-tool TOCTOU) | ❌→✅ **FIXED** | the existence sweep used a bare `_err(f"source not found: {p}")` (no `error_type`/`suggestion`); now `missing_file(p, "source angle")` |
| source deleted *between* the existence sweep and the per-source duration probe (intra-call TOCTOU) | ❌→✅ **FIXED** | added a per-source existence re-check before probing → `missing_file`; the old duration-probe failure used a bare `_err` → now `missing_file`/`media_unreadable` |
| corrupt project | ❌→✅ **FIXED** | `_load` `ProjectParseError` now → `corrupt_project` (was `operation_failed`) |
| state on any of these | ✅ project byte-identical, no snapshot, no new tracks | all checks precede the snapshot/mutation |

---

## Fixes made (all in `src`)

1. **`adapters/render/executor.py`** — `execute_render` now discards a
   newly-created partial output file on every failure/timeout/error path
   (`_discard_partial_output`); a pre-existing output is never touched. Closes the
   interrupted-render partial-artifact gap (§3).
2. **`server/bundles/clip_place.py`** — (a) `clip_place`/`clip_place_matched`
   reject a missing media *path* with `missing_file` before any snapshot/write
   (§1 false-success); (b) `clip_place`/`clip_move_to`/`clip_place_matched`
   `_load` now routes `ProjectParseError` → `corrupt_project` (§2).
3. **`server/bundles/multicam.py`** — deleted-source TOCTOU → `missing_file`
   (both the pre-call sweep and a new intra-call re-check), duration-probe
   failure → `media_unreadable`, and `_load` `ProjectParseError` →
   `corrupt_project` (§7 + §2).
4. **`server/tools/effects_color.py`** — `effect_color_grade`, `color_apply_lut`,
   `effect_color_wash`, `effect_scifi_greenscreen`, and the paper-cutout
   transition now **parse before snapshotting** and guard the parse → a corrupt
   project yields `corrupt_project` and leaks **no snapshot** (§2). Previously all
   five snapshotted first and let `ProjectParseError` escape to `operation_failed`.
5. **`server/bundles/transcript_index.py`** — `transcript_search` docstring now
   carries an explicit STALENESS CONTRACT pinning the derived-cache behavior (§6).

One existing test was updated to the improved behavior:
`test_clip_place_mcp_tools.py::test_clip_place_tool_missing_media_errors`
(was `…missing_duration_errors`, asserting the old confusing "out_seconds"
message; now asserts `missing_file` naming the media path).

## Limitations documented
- `transcript_generate` is workspace-scoped and takes no media argument, so it
  cannot name a specific moved/deleted file; it is only guaranteed never to
  fabricate a transcript for an absent asset (§1).
- `transcript_search` intentionally returns stale hits until the index is
  rebuilt; reconciliation is the caller's job (or use `shots_map_to_script`,
  which reconciles first) (§6, docstring).
- Broader observation (not exhaustively fixed): an audit of ~65 `parse_project(`
  call sites across `server/tools/` and `server/bundles/` shows the
  "unguarded parse → `operation_failed`" and "snapshot-before-parse" patterns
  recur beyond the tools exercised here. The confirmed offenders on the composed
  workflows in scope are fixed; a follow-up sweep of the remainder (e.g.
  `image_overlay`, `overlay_looks`, `timeline_audio`, `shake_shadow`, `titles`,
  `subtitle_track`) is advisable to guarantee `corrupt_project` everywhere.

## Test counts
- New: **20** tests in `tests/integration/test_workflow_failures.py` (7 scenario
  classes). All pass (68 s wall, gated tests executing against real ffmpeg/melt).
- Regression-sensitive set (render executor/pipeline, clip_place, color_grade,
  hardening/faults bundles+tools): **176 passed**, 0 regressions.
- Full suite: **4179 passed, 1 skipped** (`uv run pytest tests/ -q -p no:randomly`,
  204 s) — baseline was `4159 passed, 1 skipped`; +20 = 4179, **zero regressions,
  zero failures**.

---

# Closeout sweep — complete `parse_project` census (Pass 3 closeout)

The Pass-3a follow-up recommendation ("sweep the remainder to guarantee
`corrupt_project` everywhere") is now **done**. Every `parse_project(` call site
across `server/bundles/`, `server/tools/`, and the shared
`server/tools_helpers.py` was enumerated and classified. `ProjectParseError`
subclasses `Exception` directly (not `ValueError`), so pre-existing
`except (ValueError, FileNotFoundError)` clauses never caught it — every such
site was silently letting a corrupt project fall through to `tool_guard`'s
generic `operation_failed`. All are now routed to `corrupt_project`.

## Classification buckets
- **(a) guarded** — parse already routes `ProjectParseError → corrupt_project`
  (via `except ProjectParseError → corrupt_project(...)` or the shared
  `errors.from_exception(exc)`), and any `create_snapshot` runs *after* a
  successful parse+validate. Left untouched.
- **(b) unguarded parse** — `ProjectParseError` escaped to `operation_failed`.
  Fixed by wrapping the parse: `try: project = parse_project(...) except
  Exception as exc: return from_exception(exc)` (routes to `corrupt_project`,
  message text preserved). For shared `_load`/`_resolve_project` helpers, the
  guard was added at each tool call site.
- **(c) snapshot-before-parse** — `create_snapshot` ran *before* the parse, so a
  corrupt project both mis-reported `operation_failed` *and leaked a snapshot of
  the untouched file*. Fixed by reordering to
  parse(guarded) → validate → snapshot → serialize (matching
  `bundles/clip_place.py` / `tools/effects_color.py`).

## Site census

| bucket | count |
|---|---:|
| **Total `parse_project(` call sites** | **63** |
| (a) already guarded — left | 24 |
| best-effort helper (`subtitle_track._project_frame_count`) — intentionally left | 1 |
| (b) unguarded parse — **fixed** | 26 |
| (c) snapshot-before-parse — **fixed** | 12 |
| **Total fixed** | **38** |

`subtitle_track._project_frame_count` is a private best-effort helper that
returns a fallback frame count (bounds a melt render); it never surfaces an
error dict and takes no snapshot, so on a corrupt project it returns the
fallback rather than an error — left as-is by design. The primary parse in that
module (`subtitles_attach`) is guarded.

### Fixed-by-file
| file | fixed-b | fixed-c |
|---|---:|---:|
| bundles/image_overlay.py | 2 | 0 |
| bundles/overlay_looks.py | 1 | 1 |
| bundles/timeline_audio.py | 4 | 0 |
| bundles/titles.py | 1 | 0 |
| bundles/subtitle_track.py | 1 | 0 |
| bundles/shake_shadow.py | 1 | 1 |
| bundles/masked_wipes.py | 0 | 2 |
| bundles/shape_alpha_mask.py | 0 | 1 |
| bundles/vo_loop.py | 0 | 2 |
| bundles/split_screen.py | 0 | 1 |
| bundles/ai_mask.py | 0 | 1 |
| bundles/proxy_wiring.py | 3 | 0 |
| bundles/guides.py | 4 | 0 |
| bundles/motion_track.py | 1 | 0 |
| bundles/speed_ramp.py | 1 | 0 |
| bundles/rewind.py | 1 | 0 |
| bundles/slideshow.py | 1 | 0 |
| tools/effects_catalog.py | 2 | 1 |
| tools/effects_bundles.py | 2 | 2 |
| tools/keyframes.py | 1 | 0 |
| **totals** | **26** | **12** |

20 modules fixed. The (a)-guarded set (unchanged): `clip_place`, `multicam`,
`effects_color` (Pass-2/3a), `zoom_whip`, `pan_zoom`, `compositing_masking`,
`transitions`, `timeline_project`, `clips_nle`, `tools_helpers`
(`_load_latest_project`, guarded at all `clips_nle`/`render` callers), and the
already-correct paths in `effects_catalog`/`effects_bundles`/`keyframes`.

## Tests
New file `tests/integration/test_faults_corrupt_sweep.py` — **24 parametrized
cases**, one or more representative newly-fixed tool per module. Each feeds a
truncated `.kdenlive` and asserts: `error_type == corrupt_project`, an
actionable non-generic `suggestion`, no traceback, project bytes byte-identical,
and **`projects/snapshots/` empty** (no leaked snapshot). 18 of the 20 fixed
modules are covered here (16) plus `motion_track`/`speed_ramp` via the existing
`test_faults_bundles.py::_CORRUPT_PROJECT_TOOLS`. Two fixed modules are covered
structurally only: `ai_mask.mask_generate_and_apply` (matte generation is
engine-gated and returns `missing_dependency` before the parse when rembg is
absent) and `slideshow.media_slideshow` (image/ffmpeg-gated, no `project_file`
arg) — for both, the snapshot-leak fix is real; the `corrupt_project` route is
reachable only once the pre-parse engine/image gates pass.

## Test counts (closeout)
- New: **24** tests in `tests/integration/test_faults_corrupt_sweep.py`, all pass.
- Full suite: **4203 passed, 1 skipped** (`uv run pytest tests/ -q
  -p no:randomly`, 201 s) — baseline `4179 passed, 1 skipped`; +24 = 4203,
  **zero regressions, zero failures**. Nothing committed.
