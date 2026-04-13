---
date: 2026-04-13
topic: "Masking tools for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - masking
  - kdenlive
  - mcp
---

# Masking — Design

## Summary
Split "masking" into two conceptual families. **Localize** (alpha-bounds other effects): `mask_set` inserts a mask-producing filter (rotoscoping or object_mask), `mask_set_shape` is a rect/ellipse/polygon convenience wrapper over rotoscoping, and `mask_apply` wires a downstream effect to that mask's alpha. **Remove background** (produces transparency): `effect_chroma_key` and `effect_chroma_key_advanced` are thin wrappers over `effect_add` with typed params. Static shapes only in v1 — keyframed masks deferred to Spec 7.

## Approach Selected
**Two-family API + typed wrappers.** Mask tools handle the "alpha bounds N effects" pattern; chroma key tools handle the "make this color transparent" pattern. Composes Spec 1 (patcher extensions), Spec 2 (stack ops), Spec 3 (catalog). No new primitives in `patcher.py`.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ MCP surface (server/tools.py)                                │
│  mask_set · mask_set_shape · mask_apply                      │
│  effect_chroma_key · effect_chroma_key_advanced              │
│  effect_object_mask                                          │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/masking.py (new)                                   │
│  - Mask models (rotoscoping, object_mask, image_alpha)       │
│  - Shape-to-spline converters (rect/ellipse/polygon)         │
│  - XML builders (rotoscoping, object_mask filters)           │
│  - Alpha routing: bind target_effect to upstream mask        │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ patcher          │  │ effect_catalog   │  │ stack_ops        │
│ insert_effect_   │  │ find_by_service  │  │ serialize_stack  │
│ xml, list_effects│  │ (validate args)  │  │ (reads filters)  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

## Components

### `pipelines/masking.py` (new)

**Data model:**
```python
class MaskShape(BaseModel):
    kind: Literal["rect","ellipse","polygon"]
    bounds: tuple[float, float, float, float] = (0, 0, 1, 1)  # x,y,w,h normalized [0,1]
    points: tuple[tuple[float, float], ...] = ()  # for polygon — normalized [0,1] each

class MaskParams(BaseModel):
    points: tuple[tuple[float, float], ...]     # normalized spline points [0,1]
    feather: int = 0                             # pixel radius
    passes: int = 1                              # feather passes
    alpha_operation: Literal["write_on_clear","add","subtract","multiply","replace"] = "write_on_clear"
    spline_is_open: bool = False
```

**Functions:**
- `shape_to_points(shape: MaskShape, resolution_hint: tuple[int, int] = (1920, 1080)) -> tuple[tuple[float, float], ...]` — converts rect/ellipse/polygon to normalized point list (ellipse sampled at 32 points by default)
- `build_rotoscoping_xml(clip_ref, mask: MaskParams) -> str` — emits `<filter mlt_service="rotoscoping" track="T" clip_index="C" ...>` XML with all required `<property>` children
- `build_object_mask_xml(clip_ref, params: dict) -> str` — object_mask filter XML
- `build_chroma_key_xml(clip_ref, color, tolerance, ...) -> str` — basic chroma key (via `avfilter.colorkey` or similar — worker confirms)
- `build_chroma_key_advanced_xml(clip_ref, params: dict) -> str`
- `apply_mask_to_effect(project, clip_ref, mask_effect_index: int, target_effect_index: int) -> None` — wires target filter's alpha consumption to mask. **Implementation note:** in MLT/Kdenlive, mask-consumer filters read alpha from the stack above them; `apply_mask_to_effect` ensures `target_effect_index > mask_effect_index` (reordering via `patcher.reorder_effects` if needed) and sets any `track` / alpha-routing property on the target filter if Kdenlive's schema requires it. Worker should inspect a Kdenlive-authored rotoscoping project to confirm the exact routing mechanism.

### `edit_mcp/server/tools.py` additions

Six new `@mcp.tool()` functions:

1. **`mask_set(workspace_path, project_file, track, clip, type: str, params: str) -> dict`**
   - `type ∈ {"rotoscoping","object_mask","image_alpha"}`
   - `params` is JSON-encoded per-type param dict
   - Inserts the mask filter at the top of the clip's stack (since masks must come before effects they bound)
   - Returns `{effect_index: int, type: str, snapshot_id: str}` — effect_index is where the mask was inserted

2. **`mask_set_shape(workspace_path, project_file, track, clip, shape: str, bounds: str = "", points: str = "", feather: int = 0, alpha_operation: str = "write_on_clear") -> dict`**
   - `shape ∈ {"rect","ellipse","polygon"}`
   - `bounds` = JSON `[x,y,w,h]` normalized (rect/ellipse); `points` = JSON list for polygon
   - Converts to spline points via `shape_to_points`, then delegates to `mask_set(type="rotoscoping", ...)`
   - Returns same shape as `mask_set`

3. **`mask_apply(workspace_path, project_file, track, clip, mask_effect_index: int, target_effect_index: int) -> dict`**
   - Wires `target_effect_index` to consume alpha from `mask_effect_index`
   - Requires `mask_effect_index < target_effect_index` (reorders if not)
   - Returns `{mask_effect_index, target_effect_index, reordered: bool, snapshot_id}`

4. **`effect_chroma_key(workspace_path, project_file, track, clip, color: str = "#00FF00", tolerance: float = 0.15, blend: float = 0.0) -> dict`**
   - Typed wrapper over `effect_add` for the basic chroma key MLT filter
   - `color` accepts `#RRGGBB` → converted to MLT `0xRRGGBBAA`
   - Returns `{effect_index, snapshot_id}`

5. **`effect_chroma_key_advanced(workspace_path, project_file, track, clip, color: str, tolerance_near: float, tolerance_far: float, edge_smooth: float = 0.0, spill_suppression: float = 0.0) -> dict`**
   - Same pattern; advanced chroma key with per-edge tolerance
   - MLT service confirmed by worker via catalog lookup

6. **`effect_object_mask(workspace_path, project_file, track, clip, enabled: bool = True, threshold: float = 0.5) -> dict`**
   - Auto-subject cutout wrapper

## Data Flow

**Localize a glow effect to the clock face (Video D):**
1. `mask_set_shape(track=2, clip=4, shape="rect", bounds=[0.3, 0.2, 0.4, 0.5])` → mask at effect_index=0
2. `effect_add(track=2, clip=4, effect_name="glow", ...)` → glow at effect_index=1
3. `mask_apply(track=2, clip=4, mask_effect_index=0, target_effect_index=1)` → glow is now bounded by the rect

**Green-screen comp (Video D soldier):**
1. `effect_chroma_key_advanced(track=3, clip=0, color="#00FF00", tolerance_near=0.05, tolerance_far=0.15)` → soldier clip now transparent where green
2. (No mask needed — chroma key produces transparency directly; clip composites cleanly on lower tracks)

**Multi-mask clock (Video D clock face, numerals, center):**
1. `mask_set_shape(rect, bounds=face)` → mask_0
2. `mask_set_shape(ellipse, bounds=numerals_ring)` → mask_1
3. `mask_set_shape(rect, bounds=center_dot)` → mask_2
4. Apply effects to each via `mask_apply` with respective indices. (Multi-mask stacks = multiple `mask_set_*` calls; no special API.)

## Decisions Locked

- **Mask coordinate space:** normalized `[0, 1]` for points and bounds. Resolution-independent.
- **One mask per call.** Multiple masks = multiple calls. Each returns its own `effect_index`.
- **`mask_apply` target:** explicit `target_effect_index` (single effect per call).
- **Animated masks:** deferred. v1 supports static shapes only. Keyframe support layered on in Spec 7 via the existing keyframe tool targeting rotoscoping's point-list property.
- **Wrapper scope:** ship thin wrappers for `object_mask`, `chroma_key`, `chroma_key_advanced`.
- **`mask_set_shape` helper:** yes — supports `rect`, `ellipse` (32-point sample default), `polygon`. Converts to spline internally.
- **Mask stack position:** new masks insert at top of the clip's stack. Rationale: masks must precede the effects they bound.

## Error Handling

- **Unknown mask type** → `_err` listing the three valid values.
- **Invalid shape for `mask_set_shape`** → `_err` listing valid shapes.
- **Out-of-range bounds/points** (outside `[0,1]`) → `_err` naming the offending coordinate; tool is strict by design.
- **`mask_apply` with `mask_effect_index >= target_effect_index`** → auto-reorder target above mask via `patcher.reorder_effects`; include `reordered: true` in response.
- **`mask_apply` on a clip with fewer than 2 effects** → `_err`.
- **`mask_apply` where mask_effect_index points to a non-mask filter** (caller passed wrong index) → `_err` describing the filter type found.
- **Chroma key with invalid color format** → `_err` listing accepted formats (`#RRGGBB`, `#RRGGBBAA`, `int`).
- **Chroma key service not in catalog** (possible across Kdenlive versions) → `_err` with regeneration hint.
- **Polygon with fewer than 3 points** → `_err`.
- **Multi-mask: order matters** — caller responsibility. Tool does not re-order for them.

## Open Questions

- None. Worker will confirm the exact MLT service name for basic chroma key (`frei0r.bluescreen0r` vs `avfilter.colorkey` vs other) via catalog lookup in Sub-Spec 3.

## Approaches Considered

- **A — Two-family split + typed wrappers (selected).** Conceptually clean; separates "localize" from "remove BG".
- **B — Unified `mask_or_key` API.** Single tool with `mode` param. Rejected: different semantics (alpha source vs transparency producer) would make the tool confusing.
- **C — Animated masks in v1.** Rejected: keyframe support exists, but animating polygon splines is niche; ship static first, layer animation on top.

## Next Steps

- [ ] Turn into a Forge spec
- [ ] Spec 6 (Composite blend modes) ships next
- [ ] Spec 7 can add keyframed mask support via existing keyframe tool + rotoscoping spline property
