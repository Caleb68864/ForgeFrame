---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-ops.md"
sub_spec_number: 2
title: "Stack-Ops Pipeline Module"
date: 2026-04-13
dependencies: [1]
---

# Sub-Spec 2: Stack-Ops Pipeline Module

Refined from `docs/specs/2026-04-13-stack-ops.md` — Stack-Ops feature.

## Scope

Create a new pure-logic pipeline module `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` that:

1. Serializes a clip's filter stack into a JSON-friendly `dict`.
2. Validates and deserializes such a `dict` back into a list of filter XML strings.
3. Orchestrates `apply_paste` against a target clip in `append` | `prepend` | `replace` modes, rewriting `track=`/`clip_index=` attributes on each pasted filter.
4. Wraps `patcher.reorder_effects` in a `reorder_stack` function for symmetry with the MCP layer.

This module owns NO MCP concerns and NO filesystem I/O. It works on `KdenliveProject` instances and the patcher functions from Sub-Spec 1.

Existing pipeline siblings (e.g. `effect_apply.py`, `keyframes.py`) live in `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/` — follow their import and naming conventions.

## Interface Contracts

### Provides
- `serialize_stack(project: KdenliveProject, clip_ref: tuple[int,int]) -> dict` — returns `{"source_clip": [track, clip], "effects": [{"xml": str, "kdenlive_id": str, "mlt_service": str}, ...]}`. The `xml` field carries the verbatim `OpaqueElement.xml_string` (keyframe animation strings preserved byte-exact).
- `deserialize_stack(stack_dict: dict) -> list[str]` — validates the dict and returns the ordered list of filter XML strings. Raises `ValueError` on malformed input.
- `apply_paste(project: KdenliveProject, target_clip_ref: tuple[int,int], stack_dict: dict, mode: str) -> int` — rewrites `track=`/`clip_index=` attributes on each filter XML to match `target_clip_ref`, then inserts via `patcher.insert_effect_xml`. Returns the number of filters pasted. Modes: `append` (default), `prepend`, `replace`.
- `reorder_stack(project, clip_ref, from_index, to_index) -> None` — thin pass-through to `patcher.reorder_effects`.

### Requires
- From Sub-Spec 1: `patcher.insert_effect_xml`, `patcher.remove_effect`, `patcher.reorder_effects`.
- From Spec 1 (shipped): `patcher.list_effects`, `patcher._iter_clip_filters` (use `list_effects` for read paths in this module — `_iter_clip_filters` is private to the patcher).

### Shared State
- `KdenliveProject.opaque_elements` — mutated only via patcher functions.

## Implementation Steps

### Step 1: Write failing test
- **File:** `tests/unit/test_stack_ops_pipeline.py` (new)
- **Tests:**
  - `test_serialize_stack_three_filters` — given a clip with 3 filters, returned dict has `effects` length 3, each entry has `xml`, `kdenlive_id`, `mlt_service` keys; `source_clip == [track, clip]`.
  - `test_serialize_stack_empty` — clip with zero filters returns `{"source_clip": [...], "effects": []}` (no error).
  - `test_deserialize_stack_missing_effects_key_raises` — `deserialize_stack({"source_clip": [0,0]})` raises `ValueError` whose message mentions `effects_copy`.
  - `test_deserialize_stack_returns_xml_list` — `deserialize_stack` of a serialized stack returns a `list[str]` matching the original `xml` fields in order.
  - `test_apply_paste_append` — target clip has 2 filters; paste a 2-filter stack with `mode="append"` → target has 4 filters, original 2 first, pasted 2 last.
  - `test_apply_paste_prepend` — pasted filters appear at the top.
  - `test_apply_paste_replace` — clears target then inserts only the pasted filters.
  - `test_apply_paste_rewrites_track_clip_attrs` — source filter XML has `track="2" clip_index="0"`; paste to `(3,1)` → resulting filter XML on target has `track="3" clip_index="1"`. Use `_iter_clip_filters` on `(3,1)` to confirm match.
  - `test_apply_paste_empty_noop` — `effects: []` paste returns 0 and target stack is unchanged.
  - `test_apply_paste_invalid_mode_raises` — `mode="merge"` raises `ValueError` whose message lists `append, prepend, replace`.
  - `test_apply_paste_preserves_keyframe_strings_byte_exact` — build a filter whose `<property name="rect">` contains a keyframe animation string like `0=100 100 200 200;25=150 150 200 200`. Serialize → deserialize → apply_paste. Re-read the target filter's `rect` property; assert it equals the source byte-for-byte.
  - `test_reorder_stack_passthrough` — calling `reorder_stack(p, (2,0), 0, 2)` produces the same observable change as calling `patcher.reorder_effects` directly.
- **Run:** `uv run pytest tests/unit/test_stack_ops_pipeline.py -v`
- **Expected:** FAIL.

### Step 2: Implement `serialize_stack`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` (new)
- **Algorithm:**
  1. `filters = patcher._iter_clip_filters(project, clip_ref)` — yes, this is private but the pipeline lives inside the same edit_mcp package and Spec 1 already exposes it as the canonical iterator. Alternative: call `patcher.list_effects` for `mlt_service`/`kdenlive_id` and a parallel pass for `xml_string`.
  2. Build entries: for each `(idx, elem, root)`, append `{"xml": elem.xml_string, "kdenlive_id": <from list_effects>, "mlt_service": root.get("mlt_service") or ""}`.
  3. Return `{"source_clip": [clip_ref[0], clip_ref[1]], "effects": entries}`.

### Step 3: Implement `deserialize_stack`
- **File:** stack_ops.py
- **Algorithm:**
  1. If not isinstance(stack_dict, dict): raise `ValueError("stack must be a dict produced by effects_copy")`.
  2. If `"effects" not in stack_dict`: raise `ValueError("stack dict missing 'effects' key — did you pass the output of effects_copy?")`.
  3. If not isinstance(stack_dict["effects"], list): raise `ValueError("'effects' must be a list")`.
  4. For each entry validate it is a dict with an `"xml"` string; raise `ValueError` referencing the offending index.
  5. Return `[entry["xml"] for entry in stack_dict["effects"]]`.

### Step 4: Implement `apply_paste`
- **File:** stack_ops.py
- **Algorithm:**
  1. Validate `mode in {"append", "prepend", "replace"}`; else raise `ValueError("mode must be one of: append, prepend, replace")`.
  2. `xml_list = deserialize_stack(stack_dict)`.
  3. If `mode == "replace"`: `existing = patcher.list_effects(project, target_clip_ref)`; for each in reverse order call `patcher.remove_effect(project, target_clip_ref, idx)` (reverse so indices stay valid).
  4. Compute `base = 0` if `mode == "prepend"` else `len(patcher.list_effects(project, target_clip_ref))` (this handles both `append` and post-clear `replace`).
  5. For `i, xml in enumerate(xml_list)`: rewrite `track=` and `clip_index=` attributes on the root `<filter>` tag to `str(target_clip_ref[0])` and `str(target_clip_ref[1])`. Use `xml.etree.ElementTree.fromstring` + `set` + `tostring`, or a regex bounded to the opening tag — be mindful of preserving inner content byte-exact (use ET round-trip only on the outer attributes; if regex is safer for byte-exactness, use `re.sub` on `track="..."` and `clip_index="..."` inside the first `<filter ...>` opening tag only).
  6. Call `patcher.insert_effect_xml(project, target_clip_ref, rewritten_xml, position=base + i)`.
  7. Return `len(xml_list)`.

  **Byte-exactness note:** ET round-trip can re-order attributes and re-quote content. To satisfy the keyframe byte-exact criterion, prefer regex rewriting of just the opening-tag attributes, or use ET only when no `track`/`clip_index` attribute is present.

### Step 5: Implement `reorder_stack`
- **File:** stack_ops.py
- **Algorithm:** `patcher.reorder_effects(project, clip_ref, from_index, to_index)`. One-liner; exists for layering symmetry.

### Step 6: Verify tests pass
- **Run:** `uv run pytest tests/unit/test_stack_ops_pipeline.py -v`
- **Expected:** PASS.

### Step 7: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py tests/unit/test_stack_ops_pipeline.py`
- **Message:** `feat: stack-ops pipeline (serialize/deserialize/apply_paste)`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `serialize_stack`, `deserialize_stack`, `apply_paste`, `reorder_stack`.
- `[STRUCTURAL]` `serialize_stack` returns `{"source_clip": [track, clip], "effects": [{"xml", "kdenlive_id", "mlt_service"}, ...]}`.
- `[BEHAVIORAL]` `serialize_stack` on a 3-filter clip returns `effects` length 3.
- `[BEHAVIORAL]` `serialize_stack` on a zero-filter clip returns `effects: []`.
- `[BEHAVIORAL]` `deserialize_stack` rejects a dict missing `effects` key with a `ValueError` mentioning `effects_copy`.
- `[BEHAVIORAL]` `apply_paste(mode="append")` on a 2-filter clip with a 2-filter stack yields a 4-filter clip; original first, pasted last.
- `[BEHAVIORAL]` `apply_paste(mode="prepend")` places incoming at top.
- `[BEHAVIORAL]` `apply_paste(mode="replace")` clears then inserts; result is exactly the incoming filters.
- `[BEHAVIORAL]` `apply_paste` rewrites `track=`/`clip_index=` to match `target_clip_ref`.
- `[BEHAVIORAL]` `apply_paste` with `effects: []` is a no-op.
- `[BEHAVIORAL]` Invalid `mode` raises `ValueError` listing the three valid modes.
- `[BEHAVIORAL]` Keyframe animation strings preserved byte-exact through serialize → deserialize → apply_paste.
- `[MECHANICAL]` `uv run pytest tests/unit/test_stack_ops_pipeline.py -v` passes.

## Completeness Checklist

`serialize_stack` return shape:

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `source_clip` | `list[int, int]` | required | echoed for caller's debugging |
| `effects` | `list[dict]` | required | `deserialize_stack`, `apply_paste` |
| `effects[i].xml` | `str` (verbatim filter XML) | required | `apply_paste` (rewrites track/clip_index) |
| `effects[i].kdenlive_id` | `str` | required | LLM inspection only |
| `effects[i].mlt_service` | `str` | required | LLM inspection only |

`apply_paste` modes:
- `append` — insert at end of target's existing stack
- `prepend` — insert at start
- `replace` — clear target stack first, then insert

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_stack_ops_pipeline.py -v`
- **Regression:** `uv run pytest tests/ -v`
- **Acceptance:** unit tests directly cover each criterion; the keyframe byte-exact test covers Requirement 5 of the master spec.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py` — sibling pipeline; mirror its import style and module docstring tone.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/keyframes.py` — sibling shipped in Spec 1; shows how a pipeline calls into `patcher` functions.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:828-904` — read-side pattern (`_iter_clip_filters` + `list_effects`) for `serialize_stack`.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` | Create | Pure-logic stack serialize/deserialize/paste/reorder. |
| `tests/unit/test_stack_ops_pipeline.py` | Create | Unit tests for all four exports. |
