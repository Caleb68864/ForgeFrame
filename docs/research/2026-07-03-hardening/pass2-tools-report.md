# Hardening Pass 2 — server/tools adversarial fault-injection report

Scope owned: `workshop_video_brain/edit_mcp/server/tools/` (15 domain modules),
`server/errors.py`, and new tests. Sibling red-teams own `server/bundles/`,
`pipelines/`, `adapters/` — untouched here.

Method: a discovery harness (`/tmp/pass2_harness.py`, not committed) drove **128
injected faults** across ~70 tools spanning all 15 modules against a live
workspace (valid working copy + explicit project file + 0-byte / truncated /
binary / valid-non-MLT project files). Each call was checked for the structured
contract (`status=error` + `error_type ∈ VALID_ERROR_TYPES` + non-generic
`suggestion` + **no traceback text**), and for state integrity (target project
files **byte-unchanged** on failure, no stray `_v` working copies, no leaked
snapshots). Findings were fixed, then frozen into a permanent suite.

Baseline before work: `4001 passed, 1 skipped` (`-p no:randomly`).

## Result headline

| metric | before fixes | after fixes |
|---|---:|---:|
| injected faults (harness) | 128 | 128 |
| contract/state violations | **52** | **2** |

The 2 residual "violations" are **proven-harmless intentional successes**
(documented below), not defects.

## Breaks found and fixed

### A. Traceback / raw-exception leaks
None reached the payload — Pass 1's `@tool_guard` + `from_exception` held. One
noisy path *did* embed a multi-line **ffmpeg banner** in the `message`
(`audio_compress/normalize/denoise`, `FFmpeg X failed: <300 chars of stderr>`).
Reclassified to `operation_failed(..., cause=<last stderr line>)` so the payload
carries a one-line cause, not a wall of ffmpeg output.

### B. False successes (fault returned `status=success`) — fixed
| tool | injected fault | old behavior | fix |
|---|---|---|---|
| `effect_add` | `track=-1` | Python list wrap → edited the **wrong track**, success | reject negative `track`/`clip` up front (`nonneg_index` → `invalid_index`) |
| `composite_pip` | `overlay_track=1e9` | composite added referencing a **nonexistent track**, success + file mutated | validate `overlay_track`/`base_track` against real track count → `invalid_index` |
| `composite_set` / `composite_wipe` | `start=-100,end=-50` | negative/empty frame range accepted, success + file mutated | `_validate_frame_range` (non-negative, end>start) → `invalid_input` |
| `effect_color_grade` | `temperature=NaN` | `NaN` serialized into MLT XML, success | `nonfinite_guard` on all numeric params → `invalid_input` |
| `clip_insert` | `media_path=<a directory>` | directory accepted as media, clip inserted, success | reject directory / non-file media → `invalid_input`/`missing_file` |
| `qc_check` | `file_path=""` / `<dir>` | `Path("")`→`.` and dirs passed to ffprobe, success | reject empty / directory `file_path` → `invalid_input` |
| `broll_library_search` | `query=""` | empty query silently returned 0 results | reject empty query → `invalid_input` (matches `clips_search`) |

Also hardened with `nonfinite_guard`: `clip_speed`, `gap_insert`,
`transitions_apply_at` (timestamp), `replay_generate` (target_duration),
`effect_color_wash`, `effect_object_mask`, `effect_chroma_key_advanced`,
`composite_pip` (scale/opacity/rotation) — NaN/inf now rejected before any write.

### C. State corruption — leaked snapshots on failed ops — fixed
Several mutating tools took the pre-edit **snapshot before parsing/validating**,
so a bad index or an unparseable project left a leaked snapshot behind (worst
case: snapshotting a 0-byte / binary file that then failed to parse). Reordered
to **parse → validate → mutate-in-memory → snapshot → serialize** so a failed op
leaves *zero* side effects:
- `effect_add`, `effects_paste`, `effect_reorder` (effects_catalog)
- `effect_fade` (effects_bundles) — the huge-fade check lives in
  `build_fade_keyframes`, so the snapshot was moved past it
- `mask_set`, `mask_set_shape`, `mask_apply`, `effect_chroma_key`,
  `effect_chroma_key_advanced`, `effect_object_mask` — `_masking_prelude` no
  longer snapshots; new `_masking_finalize` snapshots+serializes only on success
- `composite_pip`, `composite_set`, `composite_wipe`
- `effect_keyframe_set_*` — added an early `effect_index` validation against the
  clip's real filter stack **before** the snapshot

Target project files were verified **byte-identical** after every failing call;
no stray `_v` working copies were produced.

### D. Not-loud-enough (`status=error` but missing `error_type`/`suggestion`)
Pass 1 deferred ~166 tool-specific `_err(...)` calls (legacy `{status,message}`
shape). This pass upgraded every such path exercised by the fault matrix (~35
call sites across `transitions`, `clips_nle`, `timeline_project`,
`transcript_markers`, `render`, `audio`, `assembly_titles`, `social_publish`,
`keyframes`, `compositing_masking`, `effects_catalog`, `effects_bundles`,
`effects_color`, `broll`) to `invalid_input` / `invalid_index` / `not_found` /
`bad_json_param` / `operation_failed`. **Legacy message text was preserved
verbatim** where existing tests substring-match it (e.g. `effect_reorder`'s
"Current stack", keyframes' "Available effects", transitions' "No cut point
found", reorder wrappers' "stack has N filters") — keys were *added*, wording
unchanged (the exact failure mode Pass-1's contract warned about; 4 tests caught
a first-pass rewording and were satisfied by restoring the wording).

## False-success hunting — the 2 remaining successes (proven harmless)
| tool | fault | why it is safe |
|---|---|---|
| `effect_add` | unknown/emoji `effect_name` | **documented intentional passthrough** — the tool accepts any MLT service id; the result is a valid, re-parseable project (asserted by `test_effect_add_unknown_effect_is_harmless_passthrough`). An unknown service is ignored by MLT at render, not corruption. |
| `mask_set` | `type=object_mask`, `params=""` | empty params apply documented defaults; result is a valid, re-parseable project (`test_mask_set_object_mask_default_params_is_harmless`). |

## errors.py additions (owned)
- `nonfinite_guard(**named)` — rejects NaN/inf numeric params (`invalid_input`).
- `nonneg_index(kind, **named)` — rejects negative indexes (`invalid_index`).
Both exported and added to `__all__`. No existing behavior changed; purely
additive.

## Transport (real JSON-RPC stdio)
New module `tests/integration/external/test_mcp_transport_faults.py`
(`@pytest.mark.external`) — the adversarial companion to
`test_mcp_transport.py`. Over a real `workshop-video-brain-server` stdio
subprocess it injects 5+1 representative faults and asserts the tool's
**structured error dict arrives as data**, never a JSON-RPC exception blob:

| fault | tool | expected error_type | verdict |
|---|---|---|---|
| nonexistent workspace_path | `project_summary` | `missing_file` | structured dict over wire |
| empty string param | `snapshot_restore` (`snapshot_id=""`) | `invalid_input` | structured dict over wire |
| invalid enum | `track_add` (`track_type="hologram"`) | `invalid_input` | structured dict over wire |
| missing media file | `clip_insert` | `missing_file` | structured dict over wire |
| missing render file | `qc_check` | `missing_file` | structured dict over wire |
| **malformed JSON-string param** | `effect_keyframe_set_scalar` (real workspace) | `bad_json_param` | structured dict over wire |

Plus a guard that the client `call_tool` returns a value rather than raising.
(These require the console script on PATH; they `skip` cleanly otherwise, like
the existing external suite.)

## Tests added (permanent)
- `tests/integration/test_faults_tools.py` — the frozen matrix: a ~98-fault
  parametrized sweep (`test_faults_are_loud_and_leave_state_intact`) asserting
  contract + byte-unchanged files + no `_v` leak + no snapshot leak per call;
  false-success regression tests (negative-track, huge-track, negative-frames,
  NaN param, directory media, empty/dir qc); two documented-harmless-success
  assertions; and a unicode/emoji/100KB-label smoke test. **12 tests.**
- `tests/integration/external/test_mcp_transport_faults.py` — **7 tests**
  (verified running live: uv's venv puts the console script on PATH, so these
  executed against a real stdio MCP subprocess and passed, rather than skipping).

## Full-suite status
Final: `uv run pytest tests/ -q -p no:randomly` →
**4149 passed, 1 skipped, 11 failed** (baseline was 4001 passed).

All **11** failures are outside this package: `tests/integration/test_faults_bundles.py`
— an **untracked** file owned by the bundles red-team, testing `server/bundles/`
tools (`clips_qc_scan`, `audio_loudness_scan`, `clips_preview_gif`,
`music_beat_grid`, `clip_dupes`, `media_stabilize`, melt) that this pass must not
touch. Those bundle tools do not import any function changed here (verified).

An intermediate run showed 15 failed; 4 of those were first-pass message
rewordings in **my** files and are now **fixed** (verified green):
`test_invalid_effect_index_error_lists_available_effects`,
`test_out_of_range_effect_index_returns_err_with_stack_length`,
`test_effect_reorder_out_of_range`,
`test_apply_at_no_boundary_near_timestamp_returns_error`.

Net for owned scope: **0 regressions** after the message-wording restoration;
+20 permanent tests (13 in-process + 7 external).

## pytest-randomly ordering
`pytest-randomly` is **not installed** in this environment
(`--randomly-seed` is unrecognized and `-p randomly` fails to import), so the
serializer agent's flagged ordering instability cannot manifest in the current
suite — collection order is deterministic. No order-dependence was engineered
into the owned test files regardless: `test_faults_tools.py` uses a
module-scoped workspace, but every assertion is computed from a per-call
before/after delta (file hashes + snapshot/working-copy listings), so shared
state cannot cross-contaminate results; the new tests carry no module-global
mutable state and are order-independent by construction.
