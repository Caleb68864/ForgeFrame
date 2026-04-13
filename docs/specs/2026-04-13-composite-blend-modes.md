# Composite Blend Modes for Kdenlive MCP

## Meta
- Client: ForgeFrame (self)
- Project: Workshop Video Brain
- Repo: /home/caleb/Projects/ForgeFrame
- Date: 2026-04-13
- Author: Caleb Bennett
- Status: completed
- Executed: 2026-04-13
- Result: 2/2 sub-specs passed (2552 tests, 0 regressions, +39 new). 20 blend modes (subtract dropped). Two-service routing: frei0r.cairoblend for named modes; qtblend for destination_in/destination_out/source_over.
- Design Doc: `docs/plans/2026-04-13-composite-blend-modes-design.md`
- Depends on shipped: Specs 1-5
- Quality Scores (7 dims / 35): Outcome 5 · Scope 5 · Decisions 5 · Edges 4 · Criteria 4 · Decomposition 4 · Purpose 5 · **Total 32/35**

## Outcome
New `composite_set` MCP tool adds a composite transition between two tracks with any of 11 blend modes (cairoblend, screen, lighten, darken, multiply, add, subtract, overlay, destination_in, destination_out, source_over). Existing `composite_pip` and `composite_wipe` tool signatures are unchanged but internally re-route through the shared pipeline function `apply_composite`. Unblocks text-as-mask compositing (destination_in), black-BG stock-overlay removal (screen), and light-layer stacking (lighten).

## Intent
**Trade-off hierarchy:**
1. Backward compatibility of `composite_pip` / `composite_wipe` over clean-slate rebuild
2. Composition over new primitives — reuse `patch_project` + `AddComposition` intent
3. Expose blend_mode as a composite transition property (per-transition control) rather than serializer-level track defaults
4. Fail loudly on unknown blend modes; do NOT pass through raw MLT strings

**Preferences:**
- Prefer keeping existing tool surfaces (`composite_pip`, `composite_wipe`)
- Prefer typed `Literal` for blend_mode enum
- Prefer reusing `_require_workspace` + `_ok` / `_err` pattern
- Prefer discovering MLT property details via catalog/XML inspection rather than hardcoding

**Escalation triggers:**
- If the MLT `compositing` property on the `composite` transition doesn't accept all 11 abstract modes OR uses different identifier strings (e.g. `dst-in` vs `destination_in`) — stop and report the mapping table for user approval.
- If the existing `AddComposition` intent cannot carry arbitrary `params` dict values (specifically the blend mode value) — stop and report before modifying the intent model.
- Any change to serializer behavior — out of scope for this spec.

## Context
Specs 1-5 shipped. Current compositing pipeline at `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py`:
- `apply_pip(project, overlay_track, base_track, start, end, layout)` — hardcoded `frei0r.cairoblend` via `composition_type="composite"`
- `apply_wipe(project, track_a, track_b, start, end, wipe_type)` — uses `composition_type="luma"` with `resource` property
- `get_pip_layout(preset, w, h, scale)` — geometry math
- `AddComposition` intent in `core/models/timeline.py` with fields `composition_type, track_a, track_b, start_frame, end_frame, params: dict`

MLT's `composite` transition has a `compositing` property (Kdenlive XML at `/usr/share/kdenlive/effects/composite.xml` — worker confirms property name and accepted value set). The abstract mode names in this spec may or may not match MLT's identifiers 1-to-1 — worker builds a mapping table if needed.

Catalog (Spec 3) contains a `composite` entry; `find_by_service("composite")` returns its `EffectDef` with full param schema.

Discussion: `EFFECTS_DISCUSSION.md`. Design: `docs/plans/2026-04-13-composite-blend-modes-design.md`.

Key files touched:
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` (extended)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)

## Requirements

1. New function `pipelines.compositing.apply_composite(project, track_a, track_b, start_frame, end_frame, blend_mode, geometry=None)` emits an `AddComposition` intent with `composition_type="composite"` and the blend mode carried in `params`.
2. `pipelines.compositing.BLEND_MODES` is a `frozenset[str]` containing exactly the 11 core modes.
3. `pipelines.compositing.BLEND_MODE_TO_MLT: dict[str, str]` maps abstract names to MLT-property values (identity mapping if MLT accepts abstract names verbatim; worker-derived mapping otherwise).
4. Existing `apply_pip` body re-routes through `apply_composite` with `blend_mode="cairoblend"` and computed geometry. Public signature unchanged.
5. Existing `apply_wipe` unchanged (uses `luma` composition — separate from composite blend modes).
6. New MCP tool `composite_set(workspace_path, project_file, track_a, track_b, start_frame, end_frame, blend_mode="cairoblend", geometry="")` registers via `@mcp.tool()` and auto-snapshots.
7. Existing MCP tools `composite_pip` and `composite_wipe` keep their signatures and behavior; only internal delegation changes for `composite_pip`.
8. Unknown blend_mode returns `_err` listing all 11 valid modes.
9. `track_a == track_b` returns `_err`.
10. `end_frame <= start_frame` returns `_err`.
11. `composite_pip` output visually unchanged (regression verification against an existing integration test or new snapshot test).
12. Full test suite passes with zero regressions.

## Sub-Specs

### Sub-Spec 1: Blend Mode Discovery + Pipeline Extension
**Scope.** Inspect Kdenlive's composite XML, determine the MLT property name and accepted blend-mode value set, and build the `BLEND_MODE_TO_MLT` mapping. Extend `pipelines.compositing` with `apply_composite` and `BLEND_MODES`/`BLEND_MODE_TO_MLT`. Pure logic.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` (extended)
- `tests/unit/test_compositing_blend_modes.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` Worker inspects `/usr/share/kdenlive/effects/composite.xml` and records the actual property name carrying blend mode (likely `compositing` but worker confirms).
- `[STRUCTURAL]` Module exports `BLEND_MODES: frozenset[str]` with exactly: `{"cairoblend","screen","lighten","darken","multiply","add","subtract","overlay","destination_in","destination_out","source_over"}`.
- `[STRUCTURAL]` Module exports `BLEND_MODE_TO_MLT: dict[str, str]` mapping each abstract name to its MLT value; identity mapping where MLT accepts the name verbatim, explicit mapping otherwise (e.g. `"destination_in" → "dst-in"` if needed).
- `[STRUCTURAL]` Module exports `apply_composite(project, track_a, track_b, start_frame, end_frame, blend_mode="cairoblend", geometry=None) -> KdenliveProject`.
- `[BEHAVIORAL]` `apply_composite` with `blend_mode="screen"` emits an `AddComposition` intent whose `params` dict contains the blend-mode key/value pair per the MLT mapping.
- `[BEHAVIORAL]` `apply_composite` with `geometry=None` emits default full-frame geometry (`"0/0:WxH:100"` where W,H come from project profile).
- `[BEHAVIORAL]` `apply_composite` with `geometry="100/50:1920x1080:75"` passes geometry through unchanged.
- `[BEHAVIORAL]` `apply_composite` with unknown `blend_mode` raises `ValueError` naming the mode and listing valid ones.
- `[BEHAVIORAL]` `apply_composite` with `track_a == track_b` raises `ValueError` with clarifying note.
- `[BEHAVIORAL]` `apply_composite` with `end_frame <= start_frame` raises `ValueError`.
- `[BEHAVIORAL]` Calling `apply_composite` returns a new `KdenliveProject` (deep copy) with the composition added; original project is unchanged.
- `[MECHANICAL]` `uv run pytest tests/unit/test_compositing_blend_modes.py -v` passes.

**Dependencies.** Spec 3 (effect_catalog for service lookup)

---

### Sub-Spec 2: Rewire apply_pip + MCP Surface
**Scope.** Rewire `apply_pip` to delegate to `apply_composite`. Register `composite_set` MCP tool. Verify `composite_pip` output is regression-identical.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` (extended — `apply_pip` body change)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `tests/integration/test_composite_set_mcp_tool.py` (new)
- `tests/unit/test_apply_pip_regression.py` (new — snapshot regression)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers `composite_set` via `@mcp.tool()`.
- `[STRUCTURAL]` `composite_set` signature: `(workspace_path: str, project_file: str, track_a: int, track_b: int, start_frame: int, end_frame: int, blend_mode: str = "cairoblend", geometry: str = "") -> dict`.
- `[STRUCTURAL]` `composite_set` return shape: `{"status","data":{"composition_added": true, "blend_mode": str, "track_a": int, "track_b": int, "snapshot_id": str}}`.
- `[STRUCTURAL]` `apply_pip` signature unchanged; body delegates to `apply_composite` with `blend_mode="cairoblend"` and geometry from `PipLayout`.
- `[STRUCTURAL]` `apply_wipe` signature and body unchanged.
- `[STRUCTURAL]` MCP `composite_pip` and `composite_wipe` signatures unchanged.
- `[INTEGRATION]` All three tools (`composite_set`, `composite_pip`, `composite_wipe`) importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` End-to-end: `composite_set(track_a=1, track_b=4, start_frame=0, end_frame=120, blend_mode="screen")` against fixture `keyframe_project.kdenlive` — re-parsing the written `.kdenlive` shows a composite transition between tracks 1 and 4 carrying the screen blend mode value.
- `[BEHAVIORAL]` `composite_set` with `blend_mode="destination_in"` writes the correct MLT value from `BLEND_MODE_TO_MLT`.
- `[BEHAVIORAL]` `composite_set` with unknown `blend_mode` returns `_err` listing all 11 valid modes.
- `[BEHAVIORAL]` `composite_set` with `track_a == track_b` returns `_err`.
- `[BEHAVIORAL]` `composite_set` with `end_frame <= start_frame` returns `_err`.
- `[BEHAVIORAL]` `composite_set` snapshot_id exists on disk after call.
- `[BEHAVIORAL]` `composite_set` with `geometry="100/50:1920x1080:75"` writes that geometry verbatim.
- `[BEHAVIORAL]` `apply_pip` regression: before and after rewire, calling `apply_pip` with the same args produces byte-identical serialized `.kdenlive` output (snapshot test against a committed expected file OR via `serialize_project` string comparison).
- `[MECHANICAL]` `uv run pytest tests/integration/test_composite_set_mcp_tool.py tests/unit/test_apply_pip_regression.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

**Dependencies.** sub-spec 1

## Edge Cases

- **blend_mode case sensitivity** — only accept lowercase abstract names; raise on `"Screen"` or `"SCREEN"` with suggestion to use lowercase.
- **geometry string with invalid format** — pass through; MLT/Kdenlive handle at parse time. Do not validate structure here.
- **composite between non-adjacent tracks** (track_a=1, track_b=4 with tracks 2 and 3 between) — allowed; MLT composites any two tracks.
- **Composition frames exceeding project duration** — allowed; matches existing `apply_pip` behavior.
- **Zero-length composition (start == end)** — rejected per requirement 10.
- **Negative track indices** — `patch_project` raises; caught by `_err` wrapping.
- **apply_pip regression** — ensure the `params` dict passed into `AddComposition` has the same key/value shape before and after rewire (e.g., don't introduce a new `compositing` key unless the old default path did so too).

## Out of Scope

- Extended blend modes (hard_light, soft_light, color_dodge, color_burn, difference, exclusion, hue, saturation, color, luminosity) — Spec 7
- Serializer track-level blend mode hardcode (`frei0r.cairoblend` default for non-composite track blending) — documented known limitation
- Clip-scoped blend modes (via alpha filters on individual clips) — different feature
- PIP preset expansion (e.g. `top_third`, `custom_grid`)
- Animated blend modes (keyframed mode changes)
- Wipe transition refactor — `apply_wipe` stays as-is
- Auto-detection of track roles (overlay vs base) from track metadata

## Constraints

### Musts
- All acceptance criteria.
- Python 3.12+, Pydantic v2.
- Reuse `AddComposition` intent — do NOT create a new intent type.
- Reuse `patch_project` — do NOT bypass it.
- `composite_pip` and `composite_wipe` public behavior unchanged (regression test).

### Must-Nots
- Must NOT modify the serializer.
- Must NOT change `AddComposition` intent field names or types.
- Must NOT accept raw MLT strings as `blend_mode` (only abstract names from `BLEND_MODES`).
- Must NOT deprecate `composite_pip` or `composite_wipe`.

### Preferences
- Prefer typed Literal for `blend_mode` at the pipeline function level (Pydantic or manual check).
- Prefer reusing `_ok` / `_err` / `_require_workspace` helpers.
- Prefer small, focused regression test for `apply_pip` (one scenario is enough).

### Escalation Triggers
- If the MLT property carrying blend mode on the `composite` transition is not `compositing`, stop and confirm the actual name.
- If the MLT value identifiers diverge from abstract names and require a non-trivial mapping table, stop and present the table for confirmation.
- If the catalog entry for `composite` lacks the blend mode parameter (meaning blend modes live on a different MLT service), stop and ask which service to use.

## Verification

1. `uv run pytest tests/ -v` passes (baseline 2513 + new tests).
2. Call `composite_set(track_a=1, track_b=2, blend_mode="screen")` on a real project; open in Kdenlive 25.x — confirm the top-track content visibly appears in screen blend mode (black pixels become transparent).
3. Call `composite_set(blend_mode="destination_in")` with text on top and video on bottom; confirm text acts as alpha mask for the video.
4. Call `composite_pip` with the same args before and after this spec; confirm output `.kdenlive` files are byte-identical via `diff`.
5. Inspect the written `.kdenlive` file; confirm composite transition carries the correct MLT property name + value pair.
