---
date: 2026-04-13
topic: "Keyframe tool for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - keyframe-tool
  - kdenlive
  - mcp
---

# Keyframe Tool -- Design

## Summary
Adds animation support to ForgeFrame's Kdenlive MCP by introducing three typed MCP tools (`effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`) plus an `effect_find` helper. All three write MLT keyframe-animation strings into `<property>` elements inside `<filter>` nodes. This is the load-bearing primitive for ~80% of techniques in the analyzed tutorial videos and must ship before transform wrappers, effect presets, or any motion-graphics workflow.

## Approach Selected
**Generic typed primitives + helper.** Three narrow tools sharing a core keyframe-serialization module, with effect targeting via `effect_index` and an `effect_find(clip, name)` helper. Per-effect wrappers (e.g. `effect_transform`) land later (Spec 7) and call into the same core.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ MCP surface (edit_mcp/server/tools.py)                      │
│  effect_keyframe_set_scalar / _rect / _color  +  effect_find│
└─────────────────────────────────────────────────────────────┘
                │                           │
                ▼                           ▼
┌───────────────────────────────┐  ┌───────────────────────────┐
│ pipelines/keyframes.py (new)  │  │ pipelines/effect_find.py  │
│  - time normalization         │  │  (new -- resolves by name)│
│  - easing resolution          │  └───────────────────────────┘
│  - keyframe string builder    │                │
│  - replace/merge logic        │                │
└───────────────────────────────┘                │
                │                                 │
                ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ adapters/kdenlive/patcher.py (extended)                     │
│  - set_effect_property(clip_ref, effect_index, prop, str)   │
│  - get_effect_property(...)  (needed for merge)             │
│  - list_effects(clip_ref)     (needed for effect_find)      │
└─────────────────────────────────────────────────────────────┘
                │
                ▼
        .kdenlive XML on disk
```

MCP tool validates input → calls `keyframes.build(...)` to produce the MLT string → patcher writes the string into the correct `<property>` node → serializer emits the updated XML. For `mode="merge"`, the pipeline reads existing property value via patcher, parses it back into keyframe objects, merges, re-serializes.

## Components

### `pipelines/keyframes.py` (new)
Owns: time normalization, easing resolution, keyframe-string serialization/parsing, replace/merge logic. Does NOT own: XML I/O, effect discovery, MCP concerns.

- `normalize_time(input, fps) -> str` -- accepts `{"frame": int}` | `{"seconds": float}` | `{"timestamp": "HH:MM:SS.mmm"}`, emits MLT timestamp.
- `resolve_easing(name_or_operator, workspace_config) -> str` -- abstract-name or raw-operator in, single-char operator out. Honors `keyframe_defaults.ease_family` from `workspace.yaml`. Defaults to `cubic` if unset.
- `build_keyframe_string(kind, keyframes, fps, config) -> str` -- emits MLT animation strings.
- `parse_keyframe_string(kind, s) -> [Keyframe]` -- inverse, needed for merge.
- `merge_keyframes(existing, new) -> [Keyframe]` -- new overwrites same-frame existing; else sorted-union.
- Schema: `Keyframe = {frame: int, value: Scalar | Rect | Color, easing: str}`.

### `pipelines/effect_find.py` (new)
- `find(project, clip_ref, name) -> int` -- raises if not found, raises if ambiguous. Matches `kdenlive_id` property if present, else `mlt_service`.

### `adapters/kdenlive/patcher.py` (extended)
- `get_effect_property(clip_ref, effect_index, property_name) -> str | None`
- `set_effect_property(clip_ref, effect_index, property_name, value: str) -> None`
- `list_effects(clip_ref) -> [{index, mlt_service, kdenlive_id, properties}]`

All three operate on the parsed in-memory project tree; serializer flushes to disk unchanged.

### `edit_mcp/server/tools.py` (extended)
Four new MCP tools:
- `effect_keyframe_set_scalar(workspace, track, clip, effect_index, property, keyframes, mode="replace")`
- `effect_keyframe_set_rect(workspace, track, clip, effect_index, property, keyframes, mode="replace")`
- `effect_keyframe_set_color(workspace, track, clip, effect_index, property, keyframes, mode="replace")`
- `effect_find(workspace, track, clip, name) -> int`

Each returns the patched project state + a snapshot id. Each auto-creates a snapshot before writing (existing project safety policy).

## Data Flow

1. Caller invokes e.g. `effect_keyframe_set_rect(workspace=..., track=2, clip=4, effect_index=0, property="rect", keyframes=[{frame:0, value:[0,0,1920,1080,1], easing:"linear"}, {seconds:2, value:[100,50,1920,1080,0.5], easing:"ease_in_out"}])`.
2. Tool layer reads workspace `workspace.yaml` for `keyframe_defaults.ease_family`, loads `.kdenlive` project via parser, pulls fps from the project's profile node.
3. `pipelines/keyframes`:
   - Normalizes each time input to `HH:MM:SS.mmm` using fps.
   - Resolves easing names to MLT operators (applying workspace `ease_family` for abstract aliases).
   - If `mode="merge"`: patcher reads existing property, `parse_keyframe_string` decodes, `merge_keyframes` combines.
   - `build_keyframe_string` emits the final MLT animation string.
4. Patcher writes the string to the target `<property>` node.
5. Serializer flushes updated XML. Snapshot id returned.

**Time conversion:** `frame / fps = seconds`, rounded to millisecond precision. Warn if conversion would collide with an adjacent keyframe's timestamp.

**Same-frame merge:** new keyframe overwrites existing at identical frame; documented in tool docstring.

**Rect values:** accept either 4-tuple `[x, y, w, h]` (implicit opacity=1) or 5-tuple `[x, y, w, h, opacity]`.

## Error Handling

- **Invalid time input** (negative frame, malformed timestamp): raise with offending key.
- **Unknown easing** (abstract name not in table, raw operator char not in MLT enum): raise listing valid set.
- **Effect index out of range / clip not found / property not on effect**: raise listing what IS available.
- **`ease_family` workspace value invalid**: fall back to `cubic`, emit a one-line warning in tool response.
- **MLT version mismatch** (workspace pins MLT <7.22, user requests `smooth_natural`/`smooth_tight`): raise with MLT version requirement. Current target MLT 7.36 makes this cold path.
- **Merge against static (non-keyframe) property value**: treat static value as a single keyframe at frame 0, then merge new keyframes in.
- **Ambiguous `effect_find`** (multiple filters with same name on a clip): raise listing all matches with their indices.

## Decisions Locked (during design discussion)

- **Time input:** union of `{frame}` | `{seconds}` | `{timestamp}`, normalized to MLT timestamp internally.
- **Tool shape:** three typed tools (scalar/rect/color) + `effect_find` helper.
- **Merge vs replace:** `mode="replace"` default; `mode="merge"` overwrites same-frame keyframes rather than stacking.
- **Easing:** accept both abstract names (`linear`, `hold`, `smooth`, `smooth_natural`, `smooth_tight`, `ease_in`, `ease_out`, `ease_in_out`, plus family variants like `ease_in_expo` / `exponential_in`) and raw MLT operators. `ease_in`/`ease_out`/`ease_in_out` family is configurable via workspace `keyframe_defaults.ease_family` (default: `cubic`). Full operator table in `EFFECTS_DISCUSSION.md`.
- **Config location:** `<workspace>/workspace.yaml` under `keyframe_defaults.ease_family`. Travels with project via `project_archive`. No MCP-global tier; fallback is hardcoded `cubic`.
- **Snapshot granularity:** auto-snapshot per MCP call (existing project default). Flag for observation if too chatty during keyframe-heavy workflows.
- **FPS source:** re-read from `.kdenlive` project profile on every call (correctness > perf).
- **Rect opacity:** accept both 4-tuple (implicit opacity=1) and 5-tuple (explicit).
- **Effect targeting:** primitive takes `effect_index`; `effect_find(clip, name) -> index` helper resolves by name.

## Open Questions

None -- all resolved during design discussion.

## Approaches Considered

- **A -- Three typed tools on shared core (selected).** Unix-style, small API surface per tool, typed values prevent LLM confusion between scalar and rect properties. Tradeoff: three tools instead of one, but each is unambiguous.
- **B -- Single polymorphic tool.** `effect_keyframe_set(kind, ...)` with `kind` discriminant. Fewer tools but fuzzier signature; LLM must remember the discriminant rule. Rejected: minor tool-count savings not worth reduced clarity.
- **C -- Per-effect wrappers only** (`effect_transform(keyframes=...)`, `effect_blur(keyframes=...)`, etc.). More ergonomic for common cases but no escape hatch for arbitrary effects. Rejected as primary surface; planned as Spec 7 layer on top of these primitives.

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-04-13-keyframe-tool-design.md`)
- [ ] Spec 2 (Stack ops -- `effects_copy`, `effects_paste`, `effect_reorder`) will build on `patcher.list_effects` added here
- [ ] Spec 3 (Catalog + generator) will let keyframe tools infer `kind` from `(effect_name, property)` automatically -- until then, caller supplies `kind` implicitly via the typed-tool choice
- [ ] Verify test fixture `.kdenlive` project exists for unit tests (`tests/integration/fixtures/`) or create one
- [ ] Document `keyframe_defaults.ease_family` in workspace.yaml schema docs
