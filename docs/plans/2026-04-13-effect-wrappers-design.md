---
date: 2026-04-13
topic: "Effect wrappers + presets for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - effect-wrappers
  - presets
  - kdenlive
  - mcp
---

# Effect Wrappers + Presets — Design

## Summary
Final spec in the Kdenlive MCP series. Three pieces: (1) a code-generator that reads the effect catalog (Spec 3) and emits typed per-effect wrapper MCP tools for commonly-used effects; (2) three high-value preset bundles demonstrated in the source tutorials (`effect_glitch_stack`, `effect_fade`, `flash_cut_montage`); (3) trivial semantic reorder wrappers (`move_to_top`, `move_up`, `move_down`, `move_to_bottom`). Skills-layer work (ff-motion-graphics, ff-effect-cookbook, etc.) explicitly deferred.

## Approach Selected
**Catalog-driven code generation + small preset library + trivial reorder wrappers.** No hand-written per-effect wrappers. All 30-ish wrappers emitted by one generator script that consumes the catalog from Spec 3. Presets compose existing primitives (effect_add, keyframe tools, clip_split). Reorder wrappers are one-line delegations to `patcher.reorder_effects`.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Generator (script + CLI subcommand)                          │
│  scripts/generate_effect_wrappers.py                         │
│  `workshop-video-brain catalog regenerate-wrappers`          │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/effect_wrapper_gen.py (new — generator logic)      │
│  - select_wrappable_effects(catalog) -> list[EffectDef]      │
│  - render_wrapper_module(effect) -> str                      │
│  - emit_wrappers_package(output_dir)                         │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/effect_wrappers/ (GENERATED package, checked in)   │
│  __init__.py — aggregates all wrapper MCP tools              │
│  effect_transform.py                                         │
│  effect_drop_shadow.py                                       │
│  effect_gaussian_blur.py                                     │
│  ... (~30 modules, one per wrappable effect)                 │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ server/tools.py — imports from effect_wrappers               │
│  Plus manually authored:                                     │
│  - Preset bundles: effect_glitch_stack, effect_fade,         │
│    flash_cut_montage                                         │
│  - Reorder wrappers: move_to_top, move_up, move_down,        │
│    move_to_bottom                                            │
└──────────────────────────────────────────────────────────────┘
```

## Components

### Generator: `pipelines/effect_wrapper_gen.py`

**Wrapper selection heuristic** (`select_wrappable_effects`):
- Must be in `effect_catalog.CATALOG`
- Category must be `"video"` (audio effects excluded — different workflow)
- Param count ≤ 8 (more than 8 → wrapper signature is noisy; caller uses `effect_add` directly)
- Must have a non-empty `display_name`
- Must have a clean `kdenlive_id` (alphanumeric + underscores/hyphens)

Result: ~30 effects from the 321-entry catalog.

**Wrapper template** (per-effect generated module):
```python
# GENERATED — do not edit by hand. Regenerate via
# workshop-video-brain catalog regenerate-wrappers
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    register_effect_wrapper,
    _require_workspace,
    _ok,
    _err,
)
from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

@register_effect_wrapper
def effect_transform(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    # params derived from catalog entry
    rect: str = "0 0 1920 1080 1",
    rotate: float = 0,
    distort: int = 0,
    compositing: int = 0,
    keyframes: str = "",  # JSON — when non-empty, params become keyframe values
) -> dict:
    """Transform filter — position, scale, rotate, opacity."""
    # Body: validate, build filter XML, insert, snapshot, return _ok
```

Param name, default, min, max come directly from catalog's `ParamDef`. Params of type `KEYFRAME`/`ANIMATED`/`GEOMETRY` trigger the `keyframes` optional param that accepts a JSON keyframe list for the animated case.

The `tools_helpers` module centralizes `_require_workspace`, `_ok`, `_err`, `register_effect_wrapper` (which wraps `@mcp.tool()` + import-tracking) to avoid import cycles.

### Preset bundles (hand-written in `server/tools.py`)

**`effect_glitch_stack(workspace_path, project_file, track, clip, intensity: float = 0.5) -> dict`**
- Inserts 5 filters in sequence: `pixeliz0r`, `glitch0r`, `rgbsplit0r`, `scanline0r`, `exposer`
- `intensity` (0..1) scales each effect's param (documented per-effect in the tool)
- Single snapshot; returns first-inserted effect_index + total count

**`effect_fade(workspace_path, project_file, track, clip, fade_in_frames: int = 0, fade_out_frames: int = 0, easing: str = "ease_in_out") -> dict`**
- Video opacity fade via transform filter with keyframed `rect`'s opacity component (5-tuple)
- Uses keyframe pipeline from Spec 1
- `fade_in_frames > 0` → opacity ramps 0→1 from clip start; `fade_out_frames > 0` → 1→0 to clip end
- Returns effect_index + snapshot_id

**`flash_cut_montage(workspace_path, project_file, track, clip, n_cuts: int = 4, blur_amount: float = 30, invert_alt: bool = True) -> dict`**
- Splits the target clip into `n_cuts` equal pieces via `clip_split`
- Adds `frei0r.directional_blur` with varying angles to each piece
- If `invert_alt`, adds `avfilter.negate` to alternating pieces
- Optionally adds transform offset to each piece (matches Video C "thunder flash")
- Returns list of created clip indices + total filter count

### Reorder semantic wrappers (hand-written in `server/tools.py`)

Four one-liner MCP tools over `patcher.reorder_effects`:
- `move_to_top(clip, effect_index)` → `reorder_effects(clip, effect_index, 0)`
- `move_to_bottom(clip, effect_index)` → `reorder_effects(clip, effect_index, len(stack)-1)`
- `move_up(clip, effect_index)` → `reorder_effects(clip, effect_index, max(0, effect_index-1))`
- `move_down(clip, effect_index)` → `reorder_effects(clip, effect_index, min(len-1, effect_index+1))`

Each snapshots, returns `{effect_index_before, effect_index_after, snapshot_id}`.

## Data Flow

**Wrapper regen:**
1. `workshop-video-brain catalog regenerate-wrappers` →
2. Script imports `effect_catalog.CATALOG` →
3. Filters via `select_wrappable_effects` →
4. Emits one Python module per effect into `pipelines/effect_wrappers/` →
5. Updates `__init__.py` with the public list →
6. Human commits the generated package

**Preset usage (glitch stack):**
1. MCP call `effect_glitch_stack(track=2, clip=4, intensity=0.7)` →
2. Tool calls `effect_add` 5 times sequentially with computed param values →
3. Single snapshot taken at start →
4. Returns summary

**Reorder:**
1. MCP call `move_to_top(track=2, clip=4, effect_index=3)` →
2. Tool reads current stack length via `patcher.list_effects` →
3. Calls `patcher.reorder_effects(clip_ref, 3, 0)` →
4. Snapshot, serialize, return.

## Decisions Locked

- **Generator over hand-written wrappers** — one-shot maintenance win.
- **Wrappable effect selection heuristic** — video-only, ≤8 params, clean id. Worker can adjust threshold if yield is < 20.
- **Ship all 3 preset bundles** — glitch_stack, fade, flash_cut_montage.
- **Skills deferred** — ff-motion-graphics, ff-effect-cookbook, etc. are separate future work (different domain: Obsidian + prompts, not Python + MCP).
- **Semantic reorder: 4 wrappers** — top/bottom/up/down.
- **Generator output location:** `pipelines/effect_wrappers/` as a package with `__init__.py`.
- **`tools_helpers` module** — extract shared MCP helpers (`_require_workspace`, `_ok`, `_err`) to a module importable by both `server/tools.py` and generated wrapper modules, avoiding a circular dep.

## Error Handling

- **Wrapper called with catalog-unknown params** (possible if wrapper was generated against an older catalog) → `_err` listing valid params for this effect.
- **Wrapper with `keyframes` JSON malformed** → `_err` with parse error.
- **Preset `effect_glitch_stack` with any of the 5 frei0r services missing from catalog** (some Kdenlive builds) → `_err` listing the missing service, suggest regenerating catalog.
- **Preset `flash_cut_montage` with `n_cuts` < 2** → `_err`.
- **Reorder wrappers on empty stack** → `_err` with stack length.
- **Reorder `move_up` when already at top (index=0)** → no-op success with note `"already at top"`.
- **Generator run with no catalog available** → `_err` pointing at `scripts/generate_effect_catalog.py`.
- **Generator regen with `--dry-run`** → writes to stdout only, doesn't touch files.

## Open Questions

- **Whether to hand-author or also auto-generate the 3 preset bundles.** Leaning hand-written — they're composition, not per-effect wrapping, and parameter tuning is subjective.
- **Whether reorder wrappers should be generated.** They're so trivial that hand-writing is fine.

Both resolved: hand-write the 4 reorder + 3 preset tools; generate only per-effect wrappers.

## Approaches Considered

- **A — Generator + 3 presets + 4 reorder (selected).** Minimal bespoke code; catalog-driven bulk.
- **B — All 30 wrappers hand-written.** Rejected — maintenance burden, drift from catalog.
- **C — Dynamic wrapper registration at server startup.** Rejected — slower startup, harder to debug, harder to test individual wrappers.
- **D — Skip wrappers, rely entirely on `effect_add` + catalog introspection.** Rejected — wrappers provide meaningful ergonomics (typed params visible in MCP schema, no JSON blob for common params).

## Next Steps

- [ ] Turn into a Forge spec
- [ ] Final MCP layer spec in the Kdenlive series
- [ ] After this: Skills layer (separate future work)
