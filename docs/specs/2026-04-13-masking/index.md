---
type: phase-spec-index
master_spec: /home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-masking.md
date: 2026-04-13
sub_specs: 3
---

# Phase Specs: Masking Tools for Kdenlive MCP

Refined from `docs/specs/2026-04-13-masking.md`.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Mask Pipeline (Shapes, XML Builders, Data Model) | Spec 3 (catalog) | [sub-spec-1-mask-pipeline.md](sub-spec-1-mask-pipeline.md) |
| 2 | Alpha Routing Logic (mask_start/mask_apply sandwich) | 1, Spec 1 (patcher) | [sub-spec-2-alpha-routing.md](sub-spec-2-alpha-routing.md) |
| 3 | MCP Tool Surface + Integration | 1, 2 | [sub-spec-3-mcp-tools.md](sub-spec-3-mcp-tools.md) |

## Critical Kdenlive Schema Discoveries

Confirmed by direct inspection of `/usr/share/kdenlive/effects/*.xml`.

### Rotoscoping (`rotoscoping.xml`)
- MLT service/tag: `rotoscoping`
- Properties (exact names):
  - `spline` — type `roto-spline`, the point list (NOT `shape`, NOT `points`)
  - `mode` — list: `alpha` | `luma` | `rgb` (default `alpha`)
  - `alpha_operation` — list: `clear` | `max` | `min` | `add` | `sub` (default `clear`) — NOTE these are the canonical values; the master spec's `"write_on_clear"` / `"subtract"` labels are UI display names. The Pydantic `alpha_operation` field must accept both UI labels and MLT values and emit the MLT value.
  - `invert` — bool (0/1)
  - `feather` — constant, max 500, min 0 (NOT `feather_passes` — that's separate)
  - `feather_passes` — constant, max 20, min 1 (maps to spec's `passes`)
- No `spline_is_open` property exists in the stock filter definition. It is documented in the master spec but is not present in Kdenlive's XML — treat as a roto-spline internal concept only; do NOT emit it.

### Mask routing — CRITICAL FINDING
Kdenlive does NOT use stack-order + `alpha_operation` to route alpha. It uses a three-part sandwich:

1. **`mask_start` filter** (or a specialized variant like `mask_start-rotoscoping`, `mask_start-shape`, `mask_start-frei0r_alphaspot`, `mask_start-frei0r_select0r`): snapshots the frame and embeds a nested filter via properties prefixed `filter.*`. The specialized variants carry a `<parameter type="fixed" name="filter" value="rotoscoping">` to declare the embedded service.
2. **Zero or more intermediate filters** on the clip — these are the effects the user wants "bounded" to the mask.
3. **`mask_apply` filter** — transitions the current frame's (masked) output back over the snapshot via `qtblend`.

This invalidates the master spec's implied model. Sub-Spec 2 MUST implement the sandwich, not alpha-operation routing. See sub-spec 2 for details.

### Chroma key effects (for Sub-Spec 1 XML builders)
- `chroma` (basic): properties `key` (color, MLT hex `0xRRGGBBAA`), `variance` (keyframable, default 0.15). NO separate `blend` property in basic chroma — the master spec's `blend` argument is accepted but ignored or mapped to `variance`-adjacent behavior. **Decision:** v1 accepts `blend` at API level but warns if non-zero; emits only `key` and `variance`.
- `frei0r.bluescreen0r` (Color-to-Alpha): properties `Invert` (bool), `Color` (color hex like `#0000ff`), `Distance` (animated, 0-1). Use for `effect_chroma_key_advanced` if `key_model="bluescreen"`.
- `avfilter.hsvkey` (advanced HSV keyer): properties `av.hue`, `av.sat`, `av.val`, `av.similarity`, `av.blend`. This is the recommended service for `effect_chroma_key_advanced` as it natively supports the `edge_smooth`/`spill_suppression`-like params via `av.similarity` and `av.blend`.
- `frei0r.keyspillm0pup`: spill suppression (referenced by catalog line ~825 "spill-suppression").

**Escalation resolution — `effect_chroma_key_advanced`:** Use `avfilter.hsvkey` as the advanced service. Document mapping in Sub-Spec 1.

### Object mask
No effect with `tag="object_mask"` exists in `/usr/share/kdenlive/effects/`. The closest candidates:
- `frei0r.alpha0ps_alphaspot` — simple shapes into alpha
- `frei0r.keyspillm0pup` — spill suppression
- No AI subject-detector ships with stock Kdenlive.

**Escalation resolution — `object_mask`:** Per master spec escalation trigger: "If `object_mask` requires an external model that isn't part of Kdenlive's stock install — stop and report." It does. **Sub-Spec 1 builds `build_object_mask_xml` as a thin wrapper over `frei0r.alpha0ps_alphaspot`** (the stock shape-into-alpha filter) with fields `enabled` (bool) and `threshold` (float 0-1 mapped to the filter's `max` property). Document this mapping clearly. Workers must NOT introduce a dependency on any external AI model.
