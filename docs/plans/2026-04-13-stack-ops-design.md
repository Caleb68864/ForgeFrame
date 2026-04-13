---
date: 2026-04-13
topic: "Effect stack operations for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - stack-ops
  - kdenlive
  - mcp
---

# Effect Stack Operations — Design

## Summary
Three MCP tools — `effects_copy`, `effects_paste`, `effect_reorder` — that manipulate a clip's filter stack as a unit. Core of the Video B paper-transition workflow ("apply rotoscope, copy effects, paste to next clip, adjust") and the Video D war-cinematic workflow ("reuse effect stack on 6+ clips"). Built on top of the `list_effects` / `get_effect_property` / `set_effect_property` primitives shipped in Spec 1 (Keyframes).

## Approach Selected
**Stateless, caller-managed clipboard + positional API primitives.** `effects_copy` returns a serialized stack dict the caller holds; `effects_paste` consumes that dict. `effect_reorder` takes `(effect_index, new_index)`. No hidden state, no session persistence, no cross-project coupling. Matches the keyframe-tool pattern (primitive first, wrappers later).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ MCP surface (edit_mcp/server/tools.py)                      │
│  effects_copy  ·  effects_paste  ·  effect_reorder          │
└─────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ pipelines/stack_ops.py (new)                                │
│  - serialize_stack(project, clip_ref, filters?) -> dict     │
│  - deserialize_stack(dict) -> list[filter_xml]              │
│  - apply_paste(project, clip_ref, stack, mode) -> project   │
│  - reorder_stack(project, clip_ref, from_idx, to_idx)       │
└─────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ adapters/kdenlive/patcher.py (already extended in Spec 1)   │
│  - list_effects (read filter stack)                          │
│  - _iter_clip_filters (private, reused)                      │
│  - new: insert_effect_xml(clip_ref, xml_string, position)    │
│  - new: remove_effect(clip_ref, effect_index)                │
│  - new: reorder_effects(clip_ref, from_idx, to_idx)          │
└─────────────────────────────────────────────────────────────┘
```

Copy returns the raw `OpaqueElement.xml_string` list for the clip's filters as a portable dict. Paste inserts those xml_strings back into the target clip's `opaque_elements`, preserving `track=`/`clip_index=` attribute rewrite. Reorder mutates position within the list.

## Components

### `pipelines/stack_ops.py` (new)
- `serialize_stack(project, clip_ref) -> dict` — returns `{"source_clip": (track, clip), "effects": [{"xml": str, "kdenlive_id": str, "mlt_service": str}, ...]}`. The `kdenlive_id`/`mlt_service` fields are echoed for caller inspection only; paste operates on `xml`.
- `deserialize_stack(stack_dict) -> list[str]` — extracts and validates the xml strings.
- `apply_paste(project, clip_ref, stack_dict, mode: Literal["append","prepend","replace"])` — rewrites `track=`/`clip_index=` attributes on each incoming filter to match target clip_ref; inserts at stack head/tail/replaces. Returns mutated project.
- `reorder_stack(project, clip_ref, from_index: int, to_index: int)` — list.insert(to_index, list.pop(from_index)) semantics on the clip's filter subset inside `project.opaque_elements`.

### `adapters/kdenlive/patcher.py` (extended)
Three new public methods — same access pattern as the Spec 1 additions:
- `insert_effect_xml(project, clip_ref, xml_string: str, position: int)` — splice into `opaque_elements` at the correct absolute position (respecting `after_tractor` placement + other filters).
- `remove_effect(project, clip_ref, effect_index: int)` — delete one filter.
- `reorder_effects(project, clip_ref, from_index: int, to_index: int)` — convenience; implemented via remove + insert.

### `edit_mcp/server/tools.py` (extended)
Three new MCP tools:
- `effects_copy(workspace_path, project_file, track, clip) -> dict` — returns `{status, data: {stack: {...}, effect_count: int}}`.
- `effects_paste(workspace_path, project_file, track, clip, stack: str (JSON), mode: str = "append") -> dict` — returns `{status, data: {effects_pasted: int, snapshot_id: str}}`.
- `effect_reorder(workspace_path, project_file, track, clip, from_index: int, to_index: int) -> dict` — returns `{status, data: {from_index, to_index, snapshot_id}}`.

Pattern mirrors Spec 1's MCP tools: `_require_workspace` → parse → operate → snapshot → serialize → `_ok(...)`.

## Data Flow

**Copy:** MCP `effects_copy(track=2, clip=4)` → parse project → patcher.list_effects + raw xml extraction via `_iter_clip_filters` → stack dict → JSON → client holds.

**Paste:** Client passes stack JSON → MCP `effects_paste(track=3, clip=1, stack=..., mode="append")` → parse project → deserialize → for each filter, rewrite `track="3" clip_index="1"` attributes → insert via `patcher.insert_effect_xml` at correct position (after existing filters on target clip in append mode; before in prepend; replace clears first) → snapshot → serialize → return.

**Reorder:** MCP `effect_reorder(track=2, clip=4, from_index=2, to_index=0)` → parse → `patcher.reorder_effects` → snapshot → serialize → return.

## Decisions Locked

- **Clipboard scope:** Stateless, caller-managed. `effects_copy` returns the stack; caller holds it (typically the LLM passing between tool calls). No `<workspace>/.clipboard/` file, no session state, no MCP-server memory.
- **Paste modes:** `append` (default), `prepend`, `replace`. All three via `mode` param.
- **`effect_reorder` API:** Positional primitive `(from_index, to_index)`. Semantic wrappers (`move_to_top`, `move_up`, etc.) deferred to Spec 7 (effect wrappers).
- **Scope:** Same-project only. Cross-project copy/paste is Spec 4 (stack presets).
- **Keyframe preservation:** Timestamps copied verbatim. No `shift_to_clip_start` in v1.

## Error Handling

- **Copy from clip with no filters** → returns `{status: "success", data: {stack: {source_clip: (t,c), effects: []}, effect_count: 0}}`. Not an error; downstream paste will no-op.
- **Paste empty stack** → no-op, returns `effects_pasted: 0` with a warning note.
- **Paste to same clip** → allowed; behaves as self-duplication in append/prepend mode, no-op effectively in replace mode.
- **Reorder out-of-range indices** → `IndexError` wrapped in `_err` with the current stack length.
- **Reorder with `from_index == to_index`** → no-op, returns success with a one-line note.
- **Malformed stack JSON on paste** → `_err` with the parse error and a pointer to `effects_copy` as the expected producer.
- **Stack with missing `track=`/`clip_index=` attributes in xml** (hand-crafted input) → attributes will be rewritten anyway; no error.

## Open Questions

- None — scope is narrow and decisions are clean.

## Approaches Considered

- **A — Stateless, caller-managed (selected).** Simplest API; no hidden state; maps cleanly onto how an LLM-driven workflow actually moves data between calls. LLM keeps the stack dict in its context or passes it through a plan.
- **B — Workspace-scoped clipboard file.** One-click reuse ("copy then paste without passing data"), but creates a hidden global that persists across unrelated calls and can go stale. Rejected: stateless is safer.
- **C — Session-scoped clipboard in MCP server memory.** Same ergonomic win as B, but bound to server lifetime. Rejected: LLMs restart; state wouldn't persist anyway; adds threading concerns.

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-04-13-stack-ops-design.md`)
- [ ] Spec 3 (Catalog + generator) still runs after this
- [ ] Semantic reorder wrappers (`move_to_top`, etc.) deferred to Spec 7
