---
type: phase-spec
master_spec: /home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-masking.md
sub_spec_number: 1
title: Mask Pipeline (Shapes, XML Builders, Data Model)
date: 2026-04-13
dependencies: ["Spec 3 (effect_catalog — shipped)"]
---

# Sub-Spec 1: Mask Pipeline (Shapes, XML Builders, Data Model)

Refined from `docs/specs/2026-04-13-masking.md`.

## Scope

Create a new, pure-logic module `pipelines/masking.py` containing:

- Pydantic data models for mask parameters and shapes.
- Shape sampling (rect, ellipse, polygon) → normalized point sequences.
- MLT XML builders for each mask service (rotoscoping, object-mask surrogate, basic chroma, advanced chroma).
- A color parser that emits MLT-canonical `0xRRGGBBAA`.

No filesystem I/O, no MCP, no KdenliveProject mutation — pure functions + Pydantic models. Follows the `pipelines/stack_ops.py` pattern: module-level regex/constants, typed helpers, thorough docstrings, no side effects.

## Interface Contracts

### Provides (consumed by Sub-Spec 2 and Sub-Spec 3)
- `MaskShape` (Pydantic v2 model): `kind: Literal["rect","ellipse","polygon"]`, `bounds: tuple[float,float,float,float] = (0,0,1,1)`, `points: tuple[tuple[float,float], ...] = ()`, `sample_count: int = 32`.
- `MaskParams` (Pydantic v2 model): `points: tuple[tuple[float,float], ...]`, `feather: int = 0`, `passes: int = 1`, `alpha_operation: Literal["clear","max","min","add","sub","write_on_clear","maximum","minimum","subtract"] = "clear"`, `spline_is_open: bool = False` (retained for future use; NOT emitted to XML — see discoveries in `index.md`).
- `shape_to_points(shape: MaskShape) -> tuple[tuple[float,float], ...]`
- `build_rotoscoping_xml(clip_ref: tuple[int,int], params: MaskParams) -> str`
- `build_object_mask_xml(clip_ref: tuple[int,int], params: dict) -> str` — wraps `frei0r.alpha0ps_alphaspot` (see index.md)
- `build_chroma_key_xml(clip_ref: tuple[int,int], color: str, tolerance: float, blend: float = 0.0) -> str` — emits `mlt_service="chroma"`
- `build_chroma_key_advanced_xml(clip_ref: tuple[int,int], color: str, tolerance_near: float, tolerance_far: float, edge_smooth: float = 0.0, spill_suppression: float = 0.0) -> str` — emits `mlt_service="avfilter.hsvkey"` with color converted to HSV
- `color_to_mlt_hex(value: str | int) -> str` — accepts `#RRGGBB`, `#RRGGBBAA`, int; returns `"0xRRGGBBAA"` (lowercase hex)
- `ALPHA_OPERATION_TO_MLT: dict[str, str]` — normalization table (e.g. `"write_on_clear" -> "clear"`, `"subtract" -> "sub"`)

### Requires
- `effect_catalog.CATALOG` (for service name lookups during builder implementation; runtime use is optional — hardcoded service names are acceptable since the catalog has been confirmed to contain the services).

### Shared State
None. Pure module.

## Implementation Steps

### Step 1: Write failing test file
- **File:** `tests/unit/test_masking_pipeline.py`
- **Pattern to follow:** `tests/unit/test_stack_ops_pipeline.py` (same test layout — no pytest fixtures for project required since module is pure).
- **Tests to add (matches acceptance criteria 1-to-1):**
  - `test_exports_present` — assert `hasattr(masking, name)` for each export.
  - `test_maskparams_defaults` — instantiate `MaskParams(points=((0,0),(1,0),(1,1),(0,1)))`, assert defaults.
  - `test_maskshape_defaults` — instantiate `MaskShape(kind="rect")`, assert defaults.
  - `test_shape_to_points_rect` — assert exactly 4 points, clockwise from top-left `(0.1,0.1)`.
  - `test_shape_to_points_ellipse` — assert 32 points; first point at `(1.0, 0.5)` (3 o'clock on unit square).
  - `test_shape_to_points_polygon_passthrough`
  - `test_shape_to_points_polygon_too_few` — `pytest.raises(ValueError, match="at least 3")`
  - `test_shape_to_points_out_of_range` — bounds `(-0.1, 0, 1, 1)` raises `ValueError` with `"-0.1"` in message.
  - `test_shape_to_points_ellipse_degenerate` — `sample_count=3` raises `ValueError`.
  - `test_build_rotoscoping_xml_structure` — parse output with `xml.etree.ElementTree`; assert `root.tag == "filter"`, `root.get("mlt_service") == "rotoscoping"`, `root.get("track") == "2"`, `root.get("clip_index") == "0"`; assert child `<property name="spline">` exists with non-empty text (JSON array of `[frame, [[x,y,linear],...]]` per Kdenlive's roto-spline format — emit a single keyframe at frame 0), `<property name="feather">5</property>`, `<property name="feather_passes">1</property>`, `<property name="alpha_operation">sub</property>` (normalized from `"subtract"`), `<property name="mode">alpha</property>`.
  - `test_build_object_mask_xml` — assert `mlt_service="frei0r.alpha0ps_alphaspot"`; assert properties for shape type, threshold.
  - `test_build_chroma_key_xml` — assert `mlt_service="chroma"`, `<property name="key">0x00ff00ff</property>`, `<property name="variance">0.15</property>`.
  - `test_build_chroma_key_advanced_xml` — assert `mlt_service="avfilter.hsvkey"` with `av.hue`, `av.sat`, `av.val`, `av.similarity`, `av.blend` properties.
  - `test_color_to_mlt_hex_cases` — all four cases from acceptance criteria.
- **Run:** `uv run pytest tests/unit/test_masking_pipeline.py -v`
- **Expected:** all FAIL (module not yet implemented).

### Step 2: Create `masking.py` scaffolding and data models
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py`
- **Action:** create
- **Pattern:** Follow `pipelines/stack_ops.py` header (docstring + `from __future__ import annotations` + `Literal` imports + module logger).
- **Add:**
  - Module docstring citing master spec and index.md.
  - `from pydantic import BaseModel, Field, field_validator`
  - `ALPHA_OPERATION_TO_MLT: dict[str,str] = {"clear":"clear","max":"max","min":"min","add":"add","sub":"sub","write_on_clear":"clear","maximum":"max","minimum":"min","subtract":"sub"}`
  - `class MaskShape(BaseModel)` with fields per interface contract. Use `field_validator("bounds","points")` to call a shared `_check_normalized` helper.
  - `class MaskParams(BaseModel)` with fields per interface contract.
  - `_check_normalized(value: float, label: str) -> None` helper raising `ValueError(f"{label}={value} out of [0,1]")`.

### Step 3: Implement `shape_to_points`
- **File:** same module
- **Action:** modify
- **Changes:**
  - `rect`: unpack `bounds=(x,y,w,h)`, return `((x,y),(x+w,y),(x+w,y+h),(x,y+h))`. Validate all four corners in `[0,1]`.
  - `ellipse`: if `sample_count < 4` raise `ValueError("ellipse sample_count must be >= 4")`. Compute center `(cx,cy) = (x+w/2, y+h/2)`, radii `(rx,ry)=(w/2,h/2)`. Loop `i in range(sample_count)`: `theta = 2*pi*i/sample_count`; point `(cx+rx*cos(theta), cy+ry*sin(theta))`. First point at angle 0 is therefore `(cx+rx, cy) = (1.0, 0.5)` when `bounds=(0,0,1,1)`.
  - `polygon`: if `len(points) < 3` raise `ValueError("polygon requires at least 3 points")`. Validate each. Return tuple unchanged.

### Step 4: Implement `color_to_mlt_hex`
- **File:** same module
- **Action:** modify
- **Pattern:** regex `^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$`. For `#RRGGBB` append `ff`. For int, format as 8-hex lowercase. Reject others with `ValueError("invalid color: {value!r} — expected #RRGGBB, #RRGGBBAA, or int")`.

### Step 5: Implement `build_rotoscoping_xml`
- **File:** same module
- **Action:** modify
- **Kdenlive roto-spline format:** The `spline` property is a JSON string keyed by frame index, where each value is a list of `[[x,y], [handle_prev_x, handle_prev_y], [handle_next_x, handle_next_y]]` entries. For v1 (linear connections per the master spec's "Out of Scope" list), emit: `json.dumps({"0": [[[x,y],[x,y],[x,y]] for (x,y) in params.points]})`. Keep the spline as a **closed** curve (v1 does not expose open splines).
- **Emit XML** (use `ET.Element` + `ET.tostring`):
  ```
  <filter mlt_service="rotoscoping" track="{t}" clip_index="{c}">
    <property name="mlt_service">rotoscoping</property>
    <property name="kdenlive_id">rotoscoping</property>
    <property name="mode">alpha</property>
    <property name="alpha_operation">{normalized}</property>
    <property name="invert">0</property>
    <property name="feather">{params.feather}</property>
    <property name="feather_passes">{params.passes}</property>
    <property name="spline">{json_spline}</property>
  </filter>
  ```
- Normalize `alpha_operation` through `ALPHA_OPERATION_TO_MLT`; if not found, raise `ValueError`.

### Step 6: Implement `build_object_mask_xml`
- **File:** same module
- **Action:** modify
- **Decision (documented in index.md):** Wraps `frei0r.alpha0ps_alphaspot`. Emit properties: `mlt_service`, `kdenlive_id=frei0r_alpha0ps_alphaspot`, `"0"` (shape selector — default `0` rectangle), `"1"` (position x, centered = `0.5`), `"2"` (position y, centered = `0.5`), `"3"` (size x, `0.5`), `"4"` (size y, `0.5`), `"5"` (tilt, `0.5`), `"6"` (alpha operation, `0`), `"7"` (threshold, from params `threshold`). Map `enabled=False` → emit `disable=1` property.
- **Note in docstring:** "Kdenlive ships no AI object-detector; this builder emulates `object_mask` via the stock alpha-spot shape filter. See `docs/specs/2026-04-13-masking/index.md` — Object mask section."

### Step 7: Implement `build_chroma_key_xml`
- **File:** same module
- **Action:** modify
- Emit `mlt_service="chroma"`, `<property name="key">{color_to_mlt_hex(color)}</property>`, `<property name="variance">{tolerance}</property>`, `<property name="kdenlive_id">chroma</property>`. If `blend` != 0, log a warning (`logger.warning`) that basic chroma ignores blend; do not emit a `blend` property.

### Step 8: Implement `build_chroma_key_advanced_xml`
- **File:** same module
- **Action:** modify
- Emit `mlt_service="avfilter.hsvkey"`. Convert the input `color` (hex) to HSV (`colorsys.rgb_to_hsv`); emit `av.hue` in degrees (0-360), `av.sat`, `av.val`. Map:
  - `tolerance_near` → `av.similarity` (range 0-1).
  - `tolerance_far` → clamped to `>= tolerance_near`; if `tolerance_far < tolerance_near` raise `ValueError("tolerance_far must be >= tolerance_near")`.
  - `edge_smooth` → `av.blend` (range 0-1).
  - `spill_suppression` → emit a second sibling filter `frei0r.keyspillm0pup` ONLY if `spill_suppression > 0`; for v1 keep it simple — emit a property `av.spill_suppression={value}` on the primary filter and document that Kdenlive may ignore it (flag as follow-up). (Alternative: return two `<filter>` blocks concatenated. Choose single-filter to keep the "one effect_index returned" contract.)
- Emit `kdenlive_id="avfilter_hsvkey"`.

### Step 9: Run tests and iterate
- **Run:** `uv run pytest tests/unit/test_masking_pipeline.py -v`
- **Expected:** all PASS. Iterate if any assertions mismatch emitted XML — prefer updating the test to match real Kdenlive-compliant output if the test assumed a wrong property name (cross-check against `/usr/share/kdenlive/effects/rotoscoping.xml` or the catalog).

### Step 10: Lint and commit
- **Run:** `uv run pytest tests/ -v` — full suite should still pass.
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py tests/unit/test_masking_pipeline.py`
- **Message:** `feat: mask pipeline — shapes, xml builders, data model (sub-spec 1)`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `MaskShape`, `MaskParams`, `shape_to_points`, `build_rotoscoping_xml`, `build_object_mask_xml`, `build_chroma_key_xml`, `build_chroma_key_advanced_xml`, `color_to_mlt_hex`.
- `[STRUCTURAL]` `MaskParams` fields match interface contract above.
- `[STRUCTURAL]` `MaskShape` fields match interface contract above.
- `[BEHAVIORAL]` `shape_to_points` rect returns 4 clockwise points.
- `[BEHAVIORAL]` `shape_to_points` ellipse with `sample_count=32` returns 32 points, first at `(1, 0.5)` for unit bounds.
- `[BEHAVIORAL]` `shape_to_points` polygon passes points through.
- `[BEHAVIORAL]` Polygon with <3 points raises ValueError naming "3".
- `[BEHAVIORAL]` Out-of-range coord raises ValueError naming the offending value.
- `[BEHAVIORAL]` `build_rotoscoping_xml` emits `<filter mlt_service="rotoscoping" track="2" clip_index="0">` with `<property name="feather">5</property>`, `<property name="alpha_operation">sub</property>`, and `<property name="spline">` containing the JSON point list. **Property name is `spline`** (confirmed from `/usr/share/kdenlive/effects/rotoscoping.xml`), NOT `shape`.
- `[BEHAVIORAL]` `build_object_mask_xml` emits filter for `frei0r.alpha0ps_alphaspot`.
- `[BEHAVIORAL]` `build_chroma_key_xml` emits `chroma` filter with `key=0x00ff00ff`.
- `[BEHAVIORAL]` `build_chroma_key_advanced_xml` emits `avfilter.hsvkey` filter.
- `[BEHAVIORAL]` `color_to_mlt_hex` handles all four cases.
- `[MECHANICAL]` `uv run pytest tests/unit/test_masking_pipeline.py -v` passes.

## Completeness Checklist

### `MaskParams` fields
| Field | Type | Required | Emitted to XML? |
|-------|------|----------|-----------------|
| `points` | `tuple[tuple[float,float], ...]` | required | yes (encoded in `spline` JSON) |
| `feather` | `int` (default 0, max 500) | optional | yes (`feather`) |
| `passes` | `int` (default 1, max 20) | optional | yes (`feather_passes`) |
| `alpha_operation` | Literal (default `"clear"`) | optional | yes (normalized via `ALPHA_OPERATION_TO_MLT`) |
| `spline_is_open` | `bool` (default False) | optional | NO (retained for API symmetry; Kdenlive's filter has no such property) |

### `MaskShape` fields
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `kind` | `Literal["rect","ellipse","polygon"]` | required | shape dispatch |
| `bounds` | `tuple[float,float,float,float]` default `(0,0,1,1)` | optional | rect, ellipse |
| `points` | `tuple[tuple[float,float], ...]` default `()` | optional | polygon |
| `sample_count` | `int` default 32, min 4 | optional | ellipse |

### Resource limits
- `feather` max 500 — enforced by Pydantic `Field(le=500)` (source: `/usr/share/kdenlive/effects/rotoscoping.xml` line `max="500"`).
- `feather_passes` max 20, min 1 — `Field(ge=1, le=20)`.
- `polygon` min points: 3 — enforced in `shape_to_points`.
- `ellipse sample_count` min: 4 — enforced in `shape_to_points`.
- Coordinates: `[0, 1]` — enforced in `_check_normalized`.

## Verification Commands

- **Build:** `uv sync`
- **Unit tests:** `uv run pytest tests/unit/test_masking_pipeline.py -v`
- **Full suite:** `uv run pytest tests/ -v`

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` — module layout, regex/constants at top, typed functions, module logger via `logging.getLogger(__name__)`.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` lines 828-1000 — `ET.Element` + `ET.tostring(..., encoding="unicode")` XML construction.
- `tests/unit/test_stack_ops_pipeline.py` — test file structure and naming.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/masking.py` | Create | Pure-logic mask module |
| `tests/unit/test_masking_pipeline.py` | Create | Unit tests for this sub-spec |
