---
date: 2026-04-13
topic: "Composite blend modes for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - composite
  - kdenlive
  - mcp
---

# Composite Blend Modes — Design

## Summary
New `composite_set` MCP tool exposes the full blend-mode surface for compositions between tracks (screen, lighten, darken, multiply, add, subtract, overlay, destination_in, destination_out, source_over, cairoblend). Existing `composite_pip` and `composite_wipe` tools keep their names but re-route through a shared pipeline module. Unblocks Video C text-as-mask (destination_in), Video D black-overlay stock removal (screen), and Video D light-layer effects (lighten).

## Approach Selected
**New generic `composite_set` + shared pipeline + existing tool retention.** Pure composition over existing `patch_project` and `AddComposition` intent. Blend mode is exposed as a typed param on the composite transition between tracks. Serializer's hardcoded `frei0r.cairoblend` default for track-level blending is out of scope (known limitation, documented).

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ MCP surface (server/tools.py)                                │
│  composite_set (new)                                         │
│  composite_pip (existing — internal rewire)                  │
│  composite_wipe (existing — internal rewire)                 │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/compositing.py (extended)                          │
│  - apply_composite(track_a, track_b, frames, blend_mode,     │
│                     geometry?) -> KdenliveProject            │
│  - get_pip_layout (existing, unchanged)                      │
│  - apply_pip → delegates to apply_composite                  │
│  - apply_wipe (existing, unchanged — uses luma composition)  │
│  - BLEND_MODES: frozenset + mapping to MLT property values   │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ core/models/timeline.py (AddComposition intent — existing)   │
│  params now accepts "distort" + "disable" + "compositing"    │
│  (the actual MLT property name for blend modes per catalog)  │
└──────────────────────────────────────────────────────────────┘
```

## Components

### `pipelines/compositing.py` (extended)

**Blend mode constants:**
```python
BLEND_MODES: frozenset[str] = frozenset({
    "cairoblend",        # default — normal alpha blend
    "screen",
    "lighten",
    "darken",
    "multiply",
    "add",
    "subtract",
    "overlay",
    "destination_in",    # use bottom's alpha; keep top's color where bottom is opaque
    "destination_out",   # invert: keep top's color where bottom is transparent
    "source_over",       # default Porter-Duff over
})
```

The MLT `composite` transition's blend mode is exposed via the `compositing` property (confirmed by worker via catalog lookup / inspection of `/usr/share/kdenlive/effects/composite.xml`). Mapping:
- `"cairoblend"` → MLT `compositing` value per Kdenlive default
- Other modes → corresponding MLT identifiers (likely same names, but worker verifies)

**New function:**
```python
def apply_composite(
    project: KdenliveProject,
    track_a: int,         # bottom track (base)
    track_b: int,         # top track (overlay)
    start_frame: int,
    end_frame: int,
    blend_mode: str = "cairoblend",
    geometry: str | None = None,  # "x/y:WxH:opacity" — defaults to full-frame
) -> KdenliveProject:
    """Add a composite transition between two tracks with specified blend mode."""
```

**Existing `apply_pip` rewired:**
```python
def apply_pip(project, overlay_track, base_track, start, end, layout) -> KdenliveProject:
    geometry = f"{layout.x}/{layout.y}:{layout.width}x{layout.height}:100"
    return apply_composite(project, base_track, overlay_track, start, end,
                           blend_mode="cairoblend", geometry=geometry)
```

**Existing `apply_wipe` unchanged** — uses `luma` composition, not the `composite` service.

### `edit_mcp/server/tools.py` additions

**New `@mcp.tool()`:**
```python
def composite_set(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    blend_mode: str = "cairoblend",
    geometry: str = "",   # "x/y:WxH:opacity" — empty = full-frame
) -> dict:
    """Add a composite transition with specified blend mode between two tracks."""
```

- Returns `_ok({"composition_added": True, "blend_mode": str, "snapshot_id": str})`
- Unknown blend_mode → `_err` listing all valid modes
- `track_a == track_b` → `_err`
- `end_frame <= start_frame` → `_err`

**Existing `composite_pip` and `composite_wipe`** — internal body change only; signatures unchanged.

## Data Flow

**Video C "text-as-mask" (destination_in):**
1. Put a text layer on V3 and a video clip on V2
2. `composite_set(track_a=2, track_b=3, start=0, end=60, blend_mode="destination_in")` →
3. The text's alpha masks the video underneath; wherever text is opaque, video shows through

**Video D "black-BG stock smoke overlay" (screen):**
1. Stock smoke clip (black background) on V4 above base on V1
2. `composite_set(track_a=1, track_b=4, start=0, end=120, blend_mode="screen")` →
3. Black pixels in smoke become transparent (screen maps 0→0); white smoke plumes show through

**Existing PIP workflow (no change):**
1. `composite_pip(overlay_track=3, base_track=1, start, end, preset="top_right")` →
2. Internally delegates to `apply_composite` with `blend_mode="cairoblend"` and computed geometry

## Decisions Locked

- **Tool surface:** add new `composite_set`; rewire `composite_pip` / `composite_wipe` internals through the shared pipeline; keep their names (backward compat).
- **Blend mode set:** 11 core modes (cairoblend, screen, lighten, darken, multiply, add, subtract, overlay, destination_in, destination_out, source_over). Extended modes (hard_light, soft_light, color_dodge, color_burn, difference, exclusion, hue, saturation, color, luminosity) deferred to Spec 7.
- **Serializer track-blend hardcode:** not touched — known limitation, documented in spec. Only per-composite-transition blend modes are configurable in this spec.
- **Scope:** track-to-track transition. Clip-scoped blend modes (pseudo-blend via alpha filters on a clip) are out of scope.
- **Legacy tools kept:** `composite_pip` and `composite_wipe` retained as use-case convenience wrappers.

## Error Handling

- **Unknown blend_mode** → `_err` listing all 11 valid modes.
- **`track_a == track_b`** → `_err` with clarifying note ("composite requires two distinct tracks").
- **`end_frame <= start_frame`** → `_err` explicitly naming the constraint.
- **Out-of-range track index** → let `patch_project` raise the existing error; wrap in `_err`.
- **Unknown MLT `compositing` property value** (future Kdenlive version changes the vocabulary) → worker maps via the catalog entry at generator time; unrecognized value fails loudly at save.
- **Caller passes `frei0r.cairoblend` or other raw MLT identifier** → accept passthrough for abstract names in the frozenset; reject everything else.

## Open Questions

- **Exact MLT property name for blend mode:** worker confirms via `/usr/share/kdenlive/effects/composite.xml` inspection (likely `compositing` but might be `distort` or `operator` depending on Kdenlive version). Spec phrasing defers to worker discovery.
- **Abstract → MLT value mapping:** worker may need to test against a hand-authored Kdenlive project to verify the stored string matches our abstract name. If MLT uses different identifiers (e.g. `dst-in` instead of `destination_in`), worker builds a mapping table.

## Approaches Considered

- **A — New `composite_set` + rewire existing (selected).** Clean API surface, backward compatible, minimal reimpl.
- **B — Replace `composite_pip`/`composite_wipe` with deprecation warnings.** Cleaner long-term but breaks existing calls; unnecessary churn for in-development API.
- **C — Add `blend_mode` param to `composite_pip`.** Conflates two concerns (PIP geometry vs generic composite).
- **D — Serializer-level track blend exposure.** Would require deeper rework of serializer; separates this spec's clean pipeline work from a risky serializer change.

## Next Steps

- [ ] Turn into Forge spec
- [ ] Spec 7 (Effect wrappers) ships next — final spec
- [ ] Future: track-level blend mode via serializer rework (known limitation)
