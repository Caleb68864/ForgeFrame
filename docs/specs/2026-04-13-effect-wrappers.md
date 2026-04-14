# Effect Wrappers + Presets for Kdenlive MCP

## Meta
- Client: ForgeFrame (self)
- Project: Workshop Video Brain
- Repo: /home/caleb/Projects/ForgeFrame
- Date: 2026-04-13
- Author: Caleb Bennett
- Status: completed
- Executed: 2026-04-13
- Result: 3/3 sub-specs passed (2589 tests, 0 regressions, +37 new). 22 auto-generated effect wrappers, 3 preset bundles (glitch_stack, fade, flash_cut_montage), 4 reorder wrappers. Substitutions: frei0r.exposer→avfilter.exposure, frei0r.directional_blur→avfilter.dblur.
- Design Doc: `docs/plans/2026-04-13-effect-wrappers-design.md`
- Depends on shipped: Specs 1-6
- Quality Scores (7 dims / 35): Outcome 5 · Scope 5 · Decisions 5 · Edges 4 · Criteria 4 · Decomposition 4 · Purpose 5 · **Total 32/35**

## Outcome
Three pieces: (1) catalog-driven code generator emits per-effect wrapper MCP tools into `pipelines/effect_wrappers/` for ~30 commonly-used video effects — wrappers expose typed params with defaults/ranges from the catalog (Spec 3) and optionally accept a `keyframes` JSON param for animated filters; (2) three preset bundles: `effect_glitch_stack`, `effect_fade`, `flash_cut_montage`; (3) four semantic reorder wrappers: `move_to_top`, `move_to_bottom`, `move_up`, `move_down`. CLI subcommand `catalog regenerate-wrappers` triggers the generator.

## Intent
**Trade-off hierarchy:**
1. Catalog as single source of truth — wrappers regenerate, never drift
2. Composition over new primitives — presets and reorder are thin layers on existing tools
3. Skills layer explicitly out of scope — different domain
4. Fail loudly on catalog regressions — wrapper imports fail fast if catalog changed shape

**Preferences:**
- Prefer additive changes; do not modify Spec 1-6 public APIs
- Prefer static code generation (checked in) over runtime registration
- Prefer `tools_helpers` extraction to avoid circular imports between generated wrappers and `server/tools.py`
- Prefer typed MCP params (primitive types with defaults) over JSON blobs where possible

**Escalation triggers:**
- If fewer than 20 effects pass the wrappable-effect selection heuristic, stop and report; heuristic may need tuning.
- If a preset bundle's underlying frei0r services are missing from the catalog (not installed on target system), stop and confirm whether to ship the preset anyway with runtime error handling.
- If `clip_split` MCP tool does not exist or has a signature incompatible with `flash_cut_montage`, stop and ask.

## Context
Specs 1-6 shipped (commits 2bb76d6, ef9f0a6, 1b82240, plus presets, masking, composite). Available building blocks:
- `effect_catalog.CATALOG` — 321 entries, each with typed `ParamDef` list
- `effect_add`, keyframe tools, `clip_split`, `patcher.reorder_effects`
- `_require_workspace`, `_ok`, `_err` helpers in `server/tools.py`
- `create_snapshot` with `SnapshotRecord.snapshot_id` field

Discussion log: `EFFECTS_DISCUSSION.md`. Design: `docs/plans/2026-04-13-effect-wrappers-design.md`.

**Wrappable effect selection heuristic (initial):**
- `category == "video"`
- `len(params) <= 8`
- `kdenlive_id` alphanumeric + underscores + hyphens only
- `display_name` non-empty
- Expected yield: ~30 effects (subject to confirmation during Sub-Spec 1)

Key files touched:
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrapper_gen.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers/` (new, GENERATED — 1 `__init__.py` + ~30 modules)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools_helpers.py` (new — extracted helpers)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended — presets + reorder + import generated wrappers)
- `scripts/generate_effect_wrappers.py` (new)
- `workshop-video-brain/src/workshop_video_brain/app/cli.py` (extended — new `catalog regenerate-wrappers` subcommand)

## Requirements

1. `effect_wrapper_gen.select_wrappable_effects(catalog) -> list[EffectDef]` returns effects matching the heuristic (filter rules above).
2. `effect_wrapper_gen.render_wrapper_module(effect_def) -> str` renders a valid Python module for one wrapped effect.
3. `effect_wrapper_gen.emit_wrappers_package(effects, output_dir) -> None` writes one file per effect plus `__init__.py` that aggregates the public functions.
4. Generated wrapper modules are syntactically valid Python, importable without runtime file I/O.
5. Each wrapper is an `@mcp.tool()` named `effect_<kdenlive_id>` (e.g., `effect_transform`, `effect_drop_shadow`).
6. Wrapper signature derives directly from catalog `ParamDef`: each param becomes a typed kwarg with `default` from catalog. Animated/geometry/keyframe params additionally accept a `keyframes: str = ""` JSON-encoded list.
7. Wrapper body: validate → build filter XML → `patcher.insert_effect_xml` at end of stack → snapshot → serialize → return `_ok({"effect_index", "snapshot_id"})`.
8. `tools_helpers.py` exports `_require_workspace`, `_ok`, `_err`, `register_effect_wrapper` for shared use across `tools.py` and wrapper modules.
9. `effect_glitch_stack(track, clip, intensity)` inserts 5 filters via `effect_add` in sequence; single snapshot. Returns `{first_effect_index, filter_count, snapshot_id}`.
10. `effect_fade(track, clip, fade_in_frames, fade_out_frames, easing)` writes opacity keyframes via the Spec 1 keyframe pipeline on a transform filter's `rect` property.
11. `flash_cut_montage(track, clip, n_cuts, blur_amount, invert_alt)` uses existing `clip_split` + `effect_add` to create the montage.
12. Four reorder wrappers (`move_to_top`, `move_to_bottom`, `move_up`, `move_down`) delegate to `patcher.reorder_effects`.
13. CLI subcommand `workshop-video-brain catalog regenerate-wrappers [--output PATH]` produces the wrappers package.
14. Script `python scripts/generate_effect_wrappers.py` does the same.
15. Full test suite passes with zero regressions.

## Sub-Specs

### Sub-Spec 1: Wrapper Generator + Tool Helpers
**Scope.** Create the generator infrastructure, extract helpers, and run the generator to produce the `effect_wrappers/` package.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrapper_gen.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools_helpers.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_wrappers/` (new, GENERATED package)
- `scripts/generate_effect_wrappers.py` (new)
- `workshop-video-brain/src/workshop_video_brain/app/cli.py` (extended)
- `tests/unit/test_effect_wrapper_gen.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `effect_wrapper_gen.py` exports `select_wrappable_effects`, `render_wrapper_module`, `emit_wrappers_package`, `SELECTION_HEURISTIC_DOCSTRING` (the documented filter rules).
- `[STRUCTURAL]` `tools_helpers.py` exports `_require_workspace`, `_ok`, `_err`, `register_effect_wrapper` (decorator that composes `@mcp.tool()` plus module-level export tracking).
- `[STRUCTURAL]` `server/tools.py` imports these helpers from `tools_helpers` instead of redefining (DRY refactor — no behavior change for existing tools).
- `[STRUCTURAL]` Generated `effect_wrappers/__init__.py` exposes all wrapped effect tool names.
- `[BEHAVIORAL]` `select_wrappable_effects(CATALOG)` returns ≥ 20 entries matching the heuristic.
- `[BEHAVIORAL]` `render_wrapper_module(catalog['transform'])` returns syntactically-valid Python source code containing `def effect_transform(...)`.
- `[BEHAVIORAL]` `emit_wrappers_package` writes one `.py` file per effect and updates `__init__.py`.
- `[BEHAVIORAL]` Generated modules import cleanly (`python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import effect_transform"`).
- `[BEHAVIORAL]` Wrapper for a param of type `KEYFRAME`/`ANIMATED`/`GEOMETRY` adds a `keyframes: str = ""` param.
- `[BEHAVIORAL]` Wrapper for an effect with `<=8` params generates a signature with each param as a typed kwarg (using catalog default).
- `[BEHAVIORAL]` Wrapper for an effect with `>8` params is skipped.
- `[BEHAVIORAL]` Wrapper body on call inserts a filter via `patcher.insert_effect_xml`, auto-snapshots, returns `{status, data: {effect_index, snapshot_id}}`.
- `[INTEGRATION]` All generated wrapper tools importable as callables from `workshop_video_brain.edit_mcp.pipelines.effect_wrappers`.
- `[BEHAVIORAL]` CLI `workshop-video-brain catalog regenerate-wrappers --output /tmp/test_wrappers` writes the package to the specified path.
- `[BEHAVIORAL]` Script `python scripts/generate_effect_wrappers.py --output /tmp/test_wrappers_2` same outcome.
- `[BEHAVIORAL]` Regenerating twice produces byte-identical output (idempotent, deterministic ordering).
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_wrapper_gen.py -v` passes.

**Dependencies.** Spec 3 (catalog)

---

### Sub-Spec 2: Preset Bundles
**Scope.** Hand-write the three preset MCP tools.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_presets.py` (new — helpers for the presets)
- `tests/integration/test_effect_presets.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers `effect_glitch_stack`, `effect_fade`, `flash_cut_montage` via `@mcp.tool()`.
- `[STRUCTURAL]` `pipelines/effect_presets.py` exports helper functions `glitch_stack_params(intensity)`, `build_fade_keyframes(fade_in, fade_out, total_frames, fps, easing)`, `montage_split_offsets(n_cuts, clip_duration_frames)`.
- `[BEHAVIORAL]` `effect_glitch_stack(track, clip, intensity=0.5)` inserts 5 filters in this order: `frei0r.pixeliz0r`, `frei0r.glitch0r`, `frei0r.rgbsplit0r`, `frei0r.scanline0r`, `frei0r.exposer`. Single snapshot. Returns `{first_effect_index: int, filter_count: 5, snapshot_id: str}`.
- `[BEHAVIORAL]` `effect_glitch_stack(intensity=1.0)` vs `intensity=0.0` produces different param values for the underlying filters (e.g., pixeliz0r block size scaled).
- `[BEHAVIORAL]` `effect_glitch_stack` with a frei0r service missing from catalog returns `_err` naming which service is missing.
- `[BEHAVIORAL]` `effect_fade(track, clip, fade_in_frames=30, fade_out_frames=30, easing="ease_in_out")` inserts a transform filter and writes opacity keyframes on its `rect` property. Re-parsing the project shows 2 or 4 keyframes (start + end + optional pre-fade-in/post-fade-out depending on implementation).
- `[BEHAVIORAL]` `effect_fade` with both `fade_in_frames=0` and `fade_out_frames=0` returns `_err` with message indicating at least one fade must be non-zero.
- `[BEHAVIORAL]` `effect_fade` respects the specified `easing` — verify by emitting and checking the MLT operator char on each keyframe string.
- `[BEHAVIORAL]` `flash_cut_montage(track, clip, n_cuts=4, blur_amount=30, invert_alt=True)` splits the clip via `clip_split` into 4 pieces, adds `frei0r.directional_blur` to each, adds `avfilter.negate` to alternating pieces. Returns `{split_clip_indices: list[int], filter_count: int, snapshot_id: str}`.
- `[BEHAVIORAL]` `flash_cut_montage(n_cuts=1)` returns `_err` (need at least 2 cuts).
- `[BEHAVIORAL]` Each preset takes a single snapshot at the start of the operation, not per-filter.
- `[MECHANICAL]` `uv run pytest tests/integration/test_effect_presets.py -v` passes.

**Dependencies.** Spec 1 (keyframe pipeline), Spec 2 (stack ops)

---

### Sub-Spec 3: Semantic Reorder Wrappers + Integration
**Scope.** Hand-write four trivial reorder wrappers. Verify full-suite regression.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `tests/integration/test_reorder_wrappers.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers `move_to_top`, `move_to_bottom`, `move_up`, `move_down` via `@mcp.tool()`.
- `[STRUCTURAL]` Each signature is `(workspace_path: str, project_file: str, track: int, clip: int, effect_index: int) -> dict`.
- `[STRUCTURAL]` Return shape: `{"status","data":{"effect_index_before","effect_index_after","snapshot_id"}}`.
- `[INTEGRATION]` All four tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` `move_to_top(track=2, clip=0, effect_index=3)` on a 4-filter stack moves filter 3 to index 0; `list_effects` after confirms.
- `[BEHAVIORAL]` `move_to_bottom(track=2, clip=0, effect_index=0)` on a 4-filter stack moves filter 0 to index 3.
- `[BEHAVIORAL]` `move_up(track=2, clip=0, effect_index=2)` moves to index 1; `move_up` with effect_index=0 returns `_ok` with note `"already at top"` and `effect_index_before == effect_index_after`.
- `[BEHAVIORAL]` `move_down(track=2, clip=0, effect_index=0)` moves to index 1; `move_down` at last index no-ops with note `"already at bottom"`.
- `[BEHAVIORAL]` Out-of-range `effect_index` returns `_err` listing current stack length.
- `[BEHAVIORAL]` Each write call returns a `snapshot_id` that exists on disk.
- `[MECHANICAL]` `uv run pytest tests/integration/test_reorder_wrappers.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

**Dependencies.** sub-spec 1, sub-spec 2

## Edge Cases

- **Catalog regenerated between wrapper regeneration runs** — generator uses current catalog at run time; regen produces new wrapper set.
- **Wrapper signature conflict with existing tool name** (e.g., `effect_transform` collides with some pre-existing name) — generator detects and errors before writing; report collisions explicitly.
- **Preset inserts fail partway** (e.g., 3 of 5 glitch stack filters inserted, then 4th errors) — restore via snapshot; report partial failure in `_err`.
- **Fade with `fade_in_frames + fade_out_frames > total_clip_duration`** — allowed; keyframes clamp naturally at clip boundaries.
- **Montage `n_cuts` > clip duration in frames** — `_err` with clip duration hint.
- **Reorder wrappers where stack has exactly 1 filter** — all four are no-ops with clarifying note.
- **Generator output directory already contains hand-written files** — generator refuses to write unless explicitly forced via `--force` flag (prevent accidental overwrite of non-generated modules).
- **Wrapper for a param with type `FIXED`** — include the param as a positional arg with the `FIXED` value as default; caller can override.
- **Wrapper for a param with type `HIDDEN`** — skip (not exposed to caller).

## Out of Scope

- Skills layer (ff-motion-graphics, ff-effect-cookbook, ff-silhouette-outline, ff-parallax-skybox, ff-paper-transition) — separate future work
- Auto-generation of preset bundles (hand-written; parameter tuning is subjective)
- Auto-generation of reorder wrappers (hand-written; trivial)
- Per-effect wrappers for effects with > 8 params (use `effect_add` directly)
- `keyframe_from_markers` tool — future work
- `effect_value_tweak_matrix` — future work
- `png_overlay_insert` — future work
- `clip_layer_swap_sequence` — future work
- Extended blend modes — shipped in Spec 6
- Animated masks — Spec 7 was originally proposed home; deferred as separate future work
- UI for wrapper browsing or preset discovery

## Constraints

### Musts
- All acceptance criteria.
- Python 3.12+.
- Catalog-driven wrapper generation — do NOT hand-write per-effect wrappers.
- Generated files must have a machine-readable "GENERATED" marker in the docstring.
- Regeneration must be idempotent (same catalog → same output).

### Must-Nots
- Must NOT modify Spec 1-6 public APIs.
- Must NOT hand-write per-effect wrappers in `server/tools.py`.
- Must NOT introduce runtime file I/O for wrapper imports.
- Must NOT use dynamic wrapper registration at server startup.

### Preferences
- Prefer small generated files (one effect per module) over one mega-file.
- Prefer Literal types where catalog param has a fixed value set.
- Prefer shared `tools_helpers` module over duplicating helpers.

### Escalation Triggers
- If fewer than 20 effects pass the heuristic, stop and report candidate set for heuristic tuning.
- If any preset's required frei0r service is missing from the catalog, stop and confirm handling policy.
- If `clip_split` MCP tool signature is incompatible with `flash_cut_montage`, stop and ask.
- If extracting helpers into `tools_helpers.py` cascades into breaking existing tests, stop and report.

## Verification

1. `uv run pytest tests/ -v` passes (baseline 2552 + new tests).
2. Run `workshop-video-brain catalog regenerate-wrappers` — inspect the produced `effect_wrappers/` package for reasonable module count and content quality.
3. `python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import effect_transform; print(effect_transform.__doc__)"` — confirms importable with catalog-derived docstring.
4. In a real project, call `effect_glitch_stack(intensity=0.7)` — open in Kdenlive 25.x, confirm 5 filters present on the target clip and the composite effect looks glitchy.
5. Call `effect_fade(fade_in_frames=30)` — open in Kdenlive, confirm clip fades in over 30 frames.
6. Call `flash_cut_montage(n_cuts=4)` — open in Kdenlive, confirm 4 clip segments with varying blur/invert.
7. Call `move_to_top(effect_index=3)` on a 4-filter clip — confirm the filter is now at index 0 in Kdenlive's effect stack panel.
