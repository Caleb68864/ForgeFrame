# Effects & Kdenlive Tooling — Discussion Log

Running notes for the MCP tool / skill expansion driven by the video-tutorial gap analysis (videos `iu0gI30NZ8M`, `Fh1xhOzfjBE`, `OO4STGUXWl8`, `cVCRmUXj87Q`). Append as we go.

## Source transcripts
- `transcripts/iu0gI30NZ8M.en.vtt` — reference finished piece
- `transcripts/Fh1xhOzfjBE.en.vtt` — paper-tear transition (Kdenlive)
- `transcripts/OO4STGUXWl8.en.vtt` — Kdenlive 25.04.2 motion-graphics breakdown
- `transcripts/cVCRmUXj87Q.en.vtt` — Kdenlive war-cinematic VFX pt.2

## Backlog snapshot

### P0 — foundational
- `effect_keyframe_set` — MLT keyframe strings w/ per-keyframe easing
- `effects_copy` / `effects_paste` — reuse effect stacks across clips
- `effect_reorder` — stack-order control (crop-by-padding on top, etc.)
- `frame_extract` — still from clip → bin
- `producer_add_color` / `producer_add_image`
- Expand `effect_list_common` to ~40 curated effects w/ param schemas + `keyframable` flag
- `effect_stack_preset` + `effect_stack_apply` — vault-stored named stacks
- `composite_set` w/ `blend_mode` (screen/lighten/destination-in/subtract/add)
- `composite_remove_black` — screen-blend wrapper for stock overlays
- `chroma_key_advanced`
- `rotoscoping_mask_set` (multi-mask) + `mask_apply` pairing

### P1 — ergonomic wrappers & presets
- Per-effect wrappers: `effect_transform`, drop_shadow, directional_blur, gaussian_blur, box_blur, lens_correction, color_temperature, crop_by_padding, vignette, film_grain, old_film, binarize, edge_glow, edge_detection, exposure, contrast, brightness, distort, three_way_rotate, invert, colorize, glow, denoise, bezier_curves, lift_gamma_gain
- `effect_glitch_stack` preset
- `effect_fade` (video opacity keyframes)
- `flash_cut_montage` preset (split-N + directional_blur + invert)
- `title_per_word` (VO-synced)
- `mask_apply`, `object_mask` wrappers
- `ff-silhouette-outline` skill
- `ff-parallax-skybox` skill

### P2 — orchestration & UX
- `ff-motion-graphics` skill
- `ff-paper-transition` skill
- `ff-effect-cookbook` (vault-backed)
- `keyframe_from_markers`
- `effect_value_tweak_matrix` (stack + per-clip overrides)
- `png_overlay_insert`
- `clip_layer_swap_sequence`
- `effect_catalog` MCP resource (introspectable)
- `ff-rough-cut-review` lint extensions

## Open discussion points

1. **Keyframe tool shape.** Generic `effect_keyframe_set(property, [(t, value, easing)])` vs per-effect wrappers w/ keyframes built in. Lean: ship generic primitive first, layer wrappers on top.
2. **Effect-stack preset location.** Vault (`patterns/effect-stacks/`), `forge-project.json`, or workspace `stacks/`? Vault is most reusable cross-project.
3. **Catalog source of truth.** Hand-curate vs generate from Kdenlive's `effects/*.xml` at `/usr/share/kdenlive/effects/`. Generation future-proofs as Kdenlive evolves.
4. **Masking vocabulary.** Unified `mask_set(type=..., params=...)` + `mask_apply(effect_ref)` vs separate tools for rotoscope/object_mask/chroma_key_advanced/mask_apply. Unified is cleaner for LLM reasoning.
5. **First-build scope.** Bundle all P0 in one spec, or split keyframes into its own spec since it's load-bearing?

## Decisions log

### Keyframe tool (locked 2026-04-13)
- **Time input:** accept union of `{frame}`, `{seconds}`, `{timestamp}`; convert internally to MLT `HH:MM:SS.mmm` using project fps.
- **Tool shape:** three typed tools — `effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`. Shared helper module underneath.
- **Merge vs replace:** `mode: "replace" | "merge" = "replace"`. Replace is default (predictable). Merge overwrites same-frame keyframes rather than stacking.
- **Easing:** accept both abstract names (`linear`, `smooth`, `hold`, `ease_in`, `ease_out`, `ease_in_out`) and raw MLT operators (`=`, `~=`, `|=`, `$=`, ...). Abstract→operator mapping versioned against current Kdenlive.
- **Effect targeting:** primitive takes `effect_index`; ship `effect_find(clip, name) -> index` helper alongside.

### Easing table (locked 2026-04-13)

Source: MLT 7.36 `src/framework/mlt_animation.c` `keyframe_type_map[]`.

**Core abstract names**

| Abstract | Operator | MLT enum |
|---|---|---|
| `linear` | `=` | linear |
| `hold` | `\|=` | discrete |
| `smooth` | `~=` | smooth_loose (Catmull-Rom) |
| `smooth_natural` | `$=` | smooth_natural |
| `smooth_tight` | `-=` | smooth_tight |
| `ease_in` | `g=` (default) | cubic_in (configurable) |
| `ease_out` | `h=` (default) | cubic_out (configurable) |
| `ease_in_out` | `i=` (default) | cubic_in_out (configurable) |

**`ease_in` family default is configurable** — per-project setting (`forge-project.json` → `keyframe_defaults.ease_family: "cubic"`) so tutorials that use exponential by convention can switch the default. Valid families: `sine`, `quad`, `cubic`, `quart`, `quint`, `expo`, `circ`, `back`, `elastic`, `bounce`.

**Named-family aliases** — both `ease_in_<family>` and `<family>_in` forms accepted:

| Family | in | out | in_out |
|---|---|---|---|
| sine / sinusoidal | `a=` | `b=` | `c=` |
| quad / quadratic | `d=` | `e=` | `f=` |
| cubic | `g=` | `h=` | `i=` |
| quart / quartic | `j=` | `k=` | `l=` |
| quint / quintic | `m=` | `n=` | `o=` |
| expo / exponential | `p=` | `q=` | `r=` |
| circ / circular | `s=` | `t=` | `u=` |
| back | `v=` | `w=` | `x=` |
| elastic | `y=` | `z=` | `A=` |
| bounce | `B=` | `C=` | `D=` |

**Raw pass-through** — any string ending in `=` with a recognized prefix char is accepted verbatim.

**Version guard** — `smooth_natural` (`$=`) and `smooth_tight` (`-=`) require MLT ≥ 7.22; emit warning if workspace pins older MLT. Current target is MLT 7.36 (Kdenlive 25.12).

### Effect-stack presets (locked 2026-04-13)

- **Two-tier storage.** Workspace (`<workspace>/stacks/<name>.yaml`) is default — travels with project, captured by `project_archive`. Vault (`<vault>/patterns/effect-stacks/<name>.md`) is opt-in via `effect_stack_promote` — cross-project recipe library, consumed by `ff-effect-cookbook`.
- **Lookup order on apply:** workspace first → vault fallback. Same name: workspace wins.
- **Format.** YAML both tiers. Workspace = pure YAML. Vault = Obsidian markdown w/ YAML frontmatter (same schema) + markdown body for human notes.
- **Payload.** name, version (int), created_at, updated_at, created_by, source (provenance), tags, description, effects[] (name + mlt_service + params + keyframes), apply_hints (blend_mode, track_placement, required_producers, stack_order).
- **Versioning.** Integer `version` field; bump on breaking schema/semantics changes. Plus `created_at`/`updated_at` timestamps.
- **Authorship.** Tool-only. Strict schema validation on load. Vault markdown body is the only human-editable part; frontmatter is tool-owned.
- **Tools:** `effect_stack_preset(clip, name)` saves workspace preset. `effect_stack_apply(name, clip)` applies. `effect_stack_promote(name)` copies workspace → vault. `effect_stack_list(scope="workspace"|"vault"|"all")` enumerates.

### Catalog source of truth (locked 2026-04-13)
- **Primary:** parse `/usr/share/kdenlive/effects/*.xml` at generator run.
- **Secondary:** diff against Kdenlive GitHub `data/effects/` (master) to surface upstream additions.
- **Output:** generated `effect_catalog.py` checked into repo — consumed by `effect_add`, `effect_list_common`, keyframe tools for `kind` inference.
- **Refresh:** on Kdenlive version bumps, not per-build.
- **Gotchas:** strip localized names via `*.po`; prefer XML for frei0r params, fall back to runtime introspection.

### Masking vocabulary (locked 2026-04-13)
- **Split into two concepts.**
- **Localize** (alpha-bounds *other* effects): `mask_set(clip, type, params)` where type ∈ {`rotoscoping`, `object_mask`, `image_alpha`}; paired with `mask_apply(clip, target_effect_index)` to wire downstream effect to mask.
- **Remove background** (produces transparency): `effect_chroma_key(clip, color, tolerance, ...)` and `effect_chroma_key_advanced(clip, ...)` — plain `effect_add` wrappers, no special infra.
- Supports multi-mask stacks (e.g. 3 rotoscopes on one clip as in Video D clock).

### Review & patch pass (2026-04-13)

Keyframe bundle reviewed by forge-evaluate + forge-red-team. Five critical/important patches applied:

- **C-1 Snapshot API:** `WorkspaceManager.create_snapshot` doesn't exist; existing `effect_add` and 3 other call sites are latently broken. Fix scoped into Sub-Spec 4: use `workspace.snapshot.create` directly, add `snapshot_id: str` field to `SnapshotRecord`, update all existing callers.
- **C-2a MLT operator reference:** Vendored authoritative `keyframe_type_map[]` to `docs/reference/mlt/keyframe-operators.md`. Sub-Spec 2's `_OPERATORS` dict populates from this reference.
- **C-2b MCP introspection:** Replaced speculative `mcp._tools` registry sniff with concrete `from tools import ...; assert callable(...)` check. Decorator registration is a side effect of module import.
- **C-3 Signature drift:** Master spec acceptance criteria now match phase-spec form (`workspace_path` + `project_file`, `keyframes: str` JSON-encoded).
- **I-5 Color format locked:** Input accepts `#RRGGBB` / `#RRGGBBAA` / `0xRRGGBBAA int`; output always MLT canonical `0xRRGGBBAA`.
- **I-10 `ease_family` flow-through:** Added `[INTEGRATION]` criterion asserting workspace config reaches output operator char.
- **C-4 Orphan export:** `_iter_clip_filters` marked private in Sub-Spec 1.

Latent bug flagged: `effect_add` and 3 other tool call sites silently broken (reference nonexistent `WorkspaceManager.create_snapshot`). Fix is part of Sub-Spec 4 scope.

### Build order (locked 2026-04-13)
1. Keyframes (load-bearing primitive — 3 typed tools + `effect_find`)
2. Stack ops (`effects_copy`, `effects_paste`, `effect_reorder`)
3. Catalog + generator
4. Stack presets (workspace + vault)
5. Masking (`mask_set` + `mask_apply` + chroma key wrappers)
6. Composite blend modes (refactor `composite_pip/wipe` → `composite_set`)
7. Effect wrappers + presets (transform, blur family, glitch_stack, flash_cut_montage, etc.)

## Key files
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` — keyframe, reorder, copy/paste land here
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py` — registry + wrappers
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py` — blend_mode surface
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py` — frei0r.cairoblend hardcode
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` — MCP surface
