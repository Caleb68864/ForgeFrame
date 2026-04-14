---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-wrappers.md"
sub_spec_number: 2
title: "Preset Bundles"
date: 2026-04-13
dependencies: [1]
---

# Sub-Spec 2: Preset Bundles

Refined from `docs/specs/2026-04-13-effect-wrappers.md`.

## Scope

Hand-write three preset MCP tools (`effect_glitch_stack`, `effect_fade`, `flash_cut_montage`) plus their helper module `pipelines/effect_presets.py`.

Presets operate at the Python level: they call `patcher.insert_effect_xml` directly (not `effect_add`), and `flash_cut_montage` calls the Python-level `clip_split` logic (not the MCP wrapper) to avoid MCP-in-MCP recursion. Each preset takes **one** snapshot at the start of the operation.

## CRITICAL — Catalog Verification Results (ESCALATION)

Grep against `pipelines/effect_catalog.py` produced:

| Service | Status |
|---------|--------|
| `frei0r.pixeliz0r` | PRESENT (line 3081) |
| `frei0r.glitch0r` | PRESENT (line 2818) |
| `frei0r.rgbsplit0r` | PRESENT (line 3181) |
| `frei0r.scanline0r` | PRESENT (line 3219) |
| `frei0r.exposer` | **MISSING** |
| `frei0r.directional_blur` | PRESENT (line 691) |
| `avfilter.negate` | PRESENT (line 1386) |

**Escalation per master spec line 32 and 210:** "If a preset bundle's underlying frei0r services are missing from the catalog, stop and confirm whether to ship the preset anyway with runtime error handling."

**Decision for this phase spec:** Substitute `avfilter.exposure` (kdenlive_id `avfilter_exposure`, catalog line 942) for `frei0r.exposer` in the glitch stack's fifth slot. Rationale: `avfilter.exposure` provides analogous "exposure boost" effect and is definitively in the catalog. Worker MUST verify this substitution is acceptable before implementing — if rejected, escalate to user and substitute or skip the 5th filter.

The acceptance criterion "`effect_glitch_stack` inserts 5 filters in this order: `frei0r.pixeliz0r`, `frei0r.glitch0r`, `frei0r.rgbsplit0r`, `frei0r.scanline0r`, `frei0r.exposer`" is therefore amended to use `avfilter.exposure` as the 5th filter. Update the error-handling test to confirm the graceful `_err` path for any catalog lookup miss.

## CRITICAL — `clip_split` Signature Mismatch (ESCALATION)

Master spec assumes `flash_cut_montage(track, clip, n_cuts, ...)` can call `clip_split` with `(track, clip)` addressing. Actual signature (`server/tools.py:1990`):

```python
def clip_split(workspace_path: str, clip_index: int, split_at_seconds: float = 0.0) -> dict
```

Findings:
- `clip_split` addresses clips by **global `clip_index` on playlist 0 only** (hard-coded `_resolve_playlist(project, 0)` at line 2003). It does NOT accept `(track, clip)`.
- It internally delegates to `patch_project([SplitClip(track_ref=playlist.id, clip_index=..., split_at_frame=...)])` via `patcher.patch_project`.
- It reloads, patches, and saves the project each call. Calling it N times from inside another MCP tool will cause N disk reloads and stale-indices between cuts (each split shifts subsequent clip indices).

**Resolution for phase spec:**
1. `flash_cut_montage` MUST NOT call the `@mcp.tool()` function `clip_split`. Instead, build a list of `SplitClip` intents directly and call `patch_project` ONCE with all splits, OR call the splits sequentially re-fetching clip indices from the patched project between each call.
2. Preferred approach (simpler + deterministic): call `patch_project` with a batch of `SplitClip(track_ref=playlist.id, clip_index=<adjusted>, split_at_frame=<offset>)` intents in one pass. Confirm `patch_project` accepts batched splits (inspect `patcher.py`).
3. `flash_cut_montage` parameter contract: reuses the same addressing model as the other presets (`track: int, clip: int`). Internally resolve to `playlist_id` + `clip_index` up front.
4. Escalation backup: if `patch_project` cannot handle batched `SplitClip` operations (stale indices), implement sequential calls and recompute indices between splits — document which approach was used.

If neither works, STOP per master-spec escalation trigger.

## Interface Contracts

### Provides
- `server.tools.effect_glitch_stack(workspace_path, track, clip, intensity=0.5) -> dict` — `@mcp.tool()`.
- `server.tools.effect_fade(workspace_path, track, clip, fade_in_frames=30, fade_out_frames=30, easing="ease_in_out") -> dict` — `@mcp.tool()`.
- `server.tools.flash_cut_montage(workspace_path, track, clip, n_cuts=4, blur_amount=30.0, invert_alt=True) -> dict` — `@mcp.tool()`.
- `pipelines.effect_presets.glitch_stack_params(intensity: float) -> dict[str, dict[str, str]]` — returns per-service property map.
- `pipelines.effect_presets.build_fade_keyframes(fade_in_frames, fade_out_frames, total_frames, fps, easing) -> list[Keyframe]`.
- `pipelines.effect_presets.montage_split_offsets(n_cuts: int, clip_duration_frames: int) -> list[int]` — returns split frame offsets (not including 0 or total).

### Requires
- From Sub-Spec 1: `_ok`, `_err`, `_require_workspace` from `tools_helpers`.
- Shipped: `patcher.insert_effect_xml`, `patcher.patch_project`, `create_snapshot`, keyframe pipeline (`pipelines/keyframes.py` — `build_keyframe_string`, `resolve_easing`, `Keyframe`).
- Shipped: `effect_catalog.CATALOG` for parameter defaults and validation.
- Shipped: `core.models.timeline.SplitClip` for the montage.

### Shared State
- Each preset takes exactly one `create_snapshot` call BEFORE any mutation, and rolls back on partial failure by restoring from that snapshot.

## Implementation Steps

### Step 1: Catalog-miss guard tests
- **File:** `tests/integration/test_effect_presets.py`
- **Test:** `test_glitch_stack_reports_missing_service` — monkeypatch CATALOG to remove one of the 5 services, call `effect_glitch_stack`, assert `_err` and the message names the missing service.
- **Run:** `uv run pytest tests/integration/test_effect_presets.py::test_glitch_stack_reports_missing_service -v`
- **Expected:** FAIL.

### Step 2: Helpers module
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_presets.py`
- **Action:** create
- **Content:**
  - `GLITCH_SERVICES: tuple[str, ...] = ("frei0r.pixeliz0r", "frei0r.glitch0r", "frei0r.rgbsplit0r", "frei0r.scanline0r", "avfilter.exposure")` — note the substitution for `frei0r.exposer`.
  - `glitch_stack_params(intensity: float) -> dict[str, dict[str, str]]` — intensity in `[0.0, 1.0]`. Clamp and raise on out-of-range. Map intensity to per-service tuneable property (e.g., pixeliz0r block size scales linearly; rgbsplit0r offset scales linearly; exposure boost scales).
  - `build_fade_keyframes(fade_in_frames, fade_out_frames, total_frames, fps, easing)` — return 2–4 `Keyframe` entries representing opacity from 0→1 over fade_in_frames, and 1→0 over fade_out_frames at end. Delegate easing resolution to `keyframes.resolve_easing`.
  - `montage_split_offsets(n_cuts, clip_duration_frames)` — return `n_cuts - 1` evenly-spaced split offsets. `n_cuts <= 1` raises `ValueError("n_cuts must be >= 2")`. `n_cuts > clip_duration_frames` raises `ValueError` with clip duration hint.

### Step 3: `effect_glitch_stack` tool + tests
- **File (test):** `tests/integration/test_effect_presets.py`
- **Tests:**
  - `test_glitch_stack_inserts_five_filters_in_order`
  - `test_glitch_stack_intensity_scales_params` — call with `intensity=0.0` and `intensity=1.0`, assert pixeliz0r block-size property differs.
  - `test_glitch_stack_single_snapshot` — count snapshots before/after; expect +1.
  - `test_glitch_stack_returns_first_effect_index_and_count`
- **File (impl):** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`
- **Impl:**
  - `@mcp.tool()` named `effect_glitch_stack`.
  - Validate inputs, `_require_workspace`, load project, for each service in `GLITCH_SERVICES` look up catalog entry; if any miss → `_err("missing catalog service: <name>")`.
  - Take snapshot ONCE.
  - For each service, build filter XML with `glitch_stack_params(intensity)[service]` merged over catalog defaults, and `patcher.insert_effect_xml(project, (track, clip), xml, position=len(list_effects(project,(track,clip))))`.
  - On any mid-insert exception, restore from snapshot and return `_err(f"partial failure after {inserted_count} filters: {exc}")`.
  - Serialize and return `_ok({"first_effect_index": <int>, "filter_count": 5, "snapshot_id": <str>})`.

### Step 4: `effect_fade` tool + tests
- **Tests:**
  - `test_fade_writes_opacity_keyframes_on_transform`
  - `test_fade_zero_zero_errors` — both frames 0 → `_err`.
  - `test_fade_easing_mlt_operator_matches` — emit `ease_in_out`, parse the resulting keyframe string, assert the MLT operator char is the expected `~` (or whatever `resolve_easing` returns).
  - `test_fade_single_snapshot`.
- **Impl:**
  - Validate: `fade_in_frames + fade_out_frames > 0`. Resolve total_frames from the clip's duration on `(track, clip)`.
  - Build `transform` filter XML (catalog `kdenlive_id='transform'`); build `rect` keyframes from `build_fade_keyframes`; format via `build_keyframe_string`.
  - Snapshot once, insert filter at end of stack, serialize.
  - Return `_ok({"effect_index", "keyframe_count", "snapshot_id"})`.

### Step 5: `flash_cut_montage` tool + tests
- **Tests:**
  - `test_montage_n_cuts_1_errors`
  - `test_montage_splits_clip_and_adds_blur_to_each_piece`
  - `test_montage_alternating_pieces_get_negate_when_invert_alt_true`
  - `test_montage_n_cuts_exceeds_duration_errors_with_hint`
  - `test_montage_single_snapshot`.
- **Impl (per escalation resolution above):**
  - Validate `n_cuts >= 2`.
  - `_require_workspace`, load project.
  - Resolve playlist (same model as `clip_split` — playlist 0 or the playlist associated with `track`; verify by reading `patcher._resolve_playlist`).
  - Compute split offsets via `montage_split_offsets`.
  - Take snapshot ONCE.
  - Build batched `SplitClip` intents and call `patch_project(project, [intents...])` in one pass. If batched splits are incorrect (indices shift), fall back to sequential: perform split, reload/refresh the in-memory project's playlist structure, recompute next clip_index, repeat.
  - Compute the list of resulting `(track, clip_index)` pairs.
  - For each resulting piece: `patcher.insert_effect_xml` with `frei0r.directional_blur` (property `blur = blur_amount`).
  - For alternating pieces (indices 1, 3, …) when `invert_alt=True`: also insert `avfilter.negate`.
  - Serialize and return `_ok({"split_clip_indices": [...], "filter_count": <int>, "snapshot_id": <str>})`.
  - On failure mid-operation, restore snapshot and `_err`.

### Step 6: Full-suite regression
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS.

### Step 7: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_presets.py workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py tests/integration/test_effect_presets.py`
- **Message:** `feat: preset bundles for glitch stack, fade, and flash cut montage`

## Acceptance Criteria

- `[STRUCTURAL]` `server/tools.py` registers `effect_glitch_stack`, `effect_fade`, `flash_cut_montage` via `@mcp.tool()`.
- `[STRUCTURAL]` `pipelines/effect_presets.py` exports `glitch_stack_params`, `build_fade_keyframes`, `montage_split_offsets`.
- `[BEHAVIORAL]` `effect_glitch_stack(...)` inserts 5 filters in order: `frei0r.pixeliz0r`, `frei0r.glitch0r`, `frei0r.rgbsplit0r`, `frei0r.scanline0r`, **`avfilter.exposure`** (substituted for missing `frei0r.exposer` — see escalation above). Single snapshot. Returns `{first_effect_index, filter_count: 5, snapshot_id}`.
- `[BEHAVIORAL]` `effect_glitch_stack(intensity=1.0)` vs `intensity=0.0` produces different per-filter property values.
- `[BEHAVIORAL]` `effect_glitch_stack` with a missing catalog service returns `_err` naming the service.
- `[BEHAVIORAL]` `effect_fade(fade_in_frames=30, fade_out_frames=30, easing="ease_in_out")` inserts a transform filter with 2–4 opacity keyframes on the `rect` property.
- `[BEHAVIORAL]` `effect_fade(fade_in_frames=0, fade_out_frames=0)` → `_err`.
- `[BEHAVIORAL]` `effect_fade` honors `easing` — MLT operator char in emitted keyframe string matches `resolve_easing(easing)`.
- `[BEHAVIORAL]` `flash_cut_montage(n_cuts=4, blur_amount=30, invert_alt=True)` splits clip into 4 pieces, adds `frei0r.directional_blur` to each, `avfilter.negate` to alternating pieces. Returns `{split_clip_indices, filter_count, snapshot_id}`.
- `[BEHAVIORAL]` `flash_cut_montage(n_cuts=1)` → `_err`.
- `[BEHAVIORAL]` Each preset takes exactly one snapshot.
- `[MECHANICAL]` `uv run pytest tests/integration/test_effect_presets.py -v` passes.

## Completeness Checklist

### `effect_glitch_stack` return

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| status | str | required | clients |
| data.first_effect_index | int | required (on success) | chained reorder |
| data.filter_count | int (== 5) | required | verification |
| data.snapshot_id | str | required | undo |
| message | str | required (on error) | clients |

### `effect_fade` return

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| data.effect_index | int | required | chaining |
| data.keyframe_count | int | required (2–4) | verification |
| data.snapshot_id | str | required | undo |

### `flash_cut_montage` return

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| data.split_clip_indices | list[int] | required | downstream labeling |
| data.filter_count | int | required | verification |
| data.snapshot_id | str | required | undo |

### Resource limits / boundaries

- `intensity` for glitch stack: clamp to `[0.0, 1.0]`; out-of-range → `_err`.
- `fade_in_frames >= 0`, `fade_out_frames >= 0`, sum > 0.
- `n_cuts >= 2`; `n_cuts <= clip_duration_frames` else `_err` with duration hint.
- `blur_amount`: use `frei0r.directional_blur` param range from catalog (line 691).
- One `create_snapshot` per preset call — enforced by test assertion on snapshot count delta.

## Verification Commands

- **Build:** `uv sync`.
- **Tests:** `uv run pytest tests/integration/test_effect_presets.py -v`; then `uv run pytest tests/ -v` for regression.
- **Manual:** Apply each preset via MCP on a smoke-test project, open in Kdenlive 25.x, confirm filter stack and visual effect.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:4896`, `:4986`, `:5082` — existing callers of `patcher.insert_effect_xml` showing XML-build + insert + serialize pattern.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py:375` — `build_keyframe_string` usage.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py:1989` — `clip_split` signature and its internal use of `SplitClip` + `patch_project` (to replicate at Python level).
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py:942` — `avfilter_exposure` definition (substitute for missing `frei0r.exposer`).

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_presets.py` | Create | Helper functions for the three presets |
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` | Modify | Add `effect_glitch_stack`, `effect_fade`, `flash_cut_montage` |
| `tests/integration/test_effect_presets.py` | Create | Preset integration tests |
