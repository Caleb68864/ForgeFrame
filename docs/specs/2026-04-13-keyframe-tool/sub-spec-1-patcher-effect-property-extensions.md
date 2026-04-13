---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-keyframe-tool.md"
sub_spec_number: 1
title: "Patcher Effect-Property Extensions"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 1: Patcher Effect-Property Extensions

Refined from spec.md — ForgeFrame keyframe tool.

## Scope

Add three module-level functions to the existing Kdenlive patcher
(`workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`)
that let callers read, write, and enumerate `<filter>` properties on a clip
without modifying any existing function.

**Important implementation note from codebase analysis.** The current
`KdenliveProject` model does NOT parse `<filter>` nodes into structured objects.
Filters are stored verbatim as `OpaqueElement(tag="filter", xml_string=...,
position_hint="after_tractor")` in `project.opaque_elements`. The existing
`_apply_add_effect` at `patcher.py:691` writes filters this way with a
`track="<track_index>"` and `clip_index="<clip_index>"` attribute on the
`<filter>` root element. The new methods below must therefore:

1. Iterate `project.opaque_elements`, keep only `tag == "filter"`.
2. Parse `xml_string` with `xml.etree.ElementTree` per-call (cheap; matches
   the "correctness > perf" trade-off in spec Intent).
3. Filter by the `track=` and `clip_index=` attributes on the `<filter>` root
   to isolate the given clip's filter stack.
4. Preserve filter order (stack order = insertion order in `opaque_elements`).
5. On `set_effect_property`, rewrite the `xml_string` in place with updated
   property content, keeping all other attributes and sibling properties
   untouched.

The `clip_ref` parameter in the sub-spec's signatures is written as a 2-tuple
`(track_index: int, clip_index: int)` — NOT a playlist string — to match the
`_apply_add_effect` pattern already in use. This replaces the sub-spec's
shorthand notation `(2,0)`.

## Interface Contracts

### Provides
- `get_effect_property(project, clip_ref, effect_index, property_name) -> str | None`
- `set_effect_property(project, clip_ref, effect_index, property_name, value) -> None` (mutates `project` in place — matches existing `_apply_*` pattern in patcher)
- `list_effects(project, clip_ref) -> list[dict]` with dict keys `{"index", "mlt_service", "kdenlive_id", "properties"}`
- An internal helper `_iter_clip_filters(project, clip_ref) -> list[tuple[int, OpaqueElement, ET.Element]]` used by all three public methods. **Private** (leading underscore — not part of the cross-spec contract). Sub-Spec 3's `effect_find.find()` consumes `list_effects` (the dict form) instead.

### Requires
None — no dependencies.

### Shared State
Operates on the same `OpaqueElement` list that `_apply_add_effect` writes. Any
serializer changes are out of scope (per master spec Must-Nots).

## Implementation Steps

### Step 1: Write failing test file
- **File:** `tests/unit/test_patcher_effect_properties.py`
- **Tests:**
  - `test_list_effects_returns_filter_stack_in_order`
  - `test_get_effect_property_returns_existing_value`
  - `test_get_effect_property_missing_property_returns_none`
  - `test_get_effect_property_bad_effect_index_raises_index_error`
  - `test_get_effect_property_bad_clip_ref_raises_index_error`
  - `test_set_effect_property_mutates_xml_string`
  - `test_set_effect_property_roundtrip_with_get`
  - `test_list_effects_empty_when_no_filters`
- **Fixture setup:** Build a `KdenliveProject` in-memory with two tracks, one clip on track 2, and two pre-existing `OpaqueElement` filter XMLs on that clip (one `affine` with `kdenlive_id="transform"` property and a `rect` string value; one `avfilter.eq` without `kdenlive_id`). Use `ET.tostring` to build the XML strings.
- **Run:** `uv run pytest tests/unit/test_patcher_effect_properties.py -v`
- **Expected:** all tests fail (module functions not yet defined).

### Step 2: Implement `_iter_clip_filters` helper
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`
- **Action:** modify (additive — add new functions at end of module, do not touch existing `_apply_*` functions)
- **Pattern:** Match the existing `_find_playlist` helper style (small, typed, returns `None` on miss). For XML parsing, use `xml.etree.ElementTree` which is already imported indirectly via the parser module; import at function top with `import xml.etree.ElementTree as ET`.
- **Changes:**
  ```python
  def _iter_clip_filters(
      project: KdenliveProject,
      clip_ref: tuple[int, int],
  ) -> list[tuple[int, "OpaqueElement", "ET.Element"]]:
      """Return [(effect_index, opaque_element, parsed_root), ...] for a clip.

      effect_index is the position of the filter within this clip's filter
      stack (0-based), NOT the index in project.opaque_elements.
      """
  ```
  Validate `clip_ref`: raise `IndexError(f"track_index {t} out of range (have {n} playlists)")` if `track` is bad; raise `IndexError(f"clip_index {c} out of range (track has {n} clips)")` if `clip` is bad.

### Step 3: Implement `list_effects`
- **File:** same patcher module.
- **Signature:** `def list_effects(project: KdenliveProject, clip_ref: tuple[int, int]) -> list[dict]:`
- **Behaviour:** walk `_iter_clip_filters`, for each parsed element extract: `index` (position in list), `mlt_service` (root `.get("mlt_service")` or `""`), `kdenlive_id` (from `<property name="kdenlive_id">` child text or `""`), `properties` (dict of every `<property name="X">text</property>` child).

### Step 4: Implement `get_effect_property`
- **Signature:** `def get_effect_property(project: KdenliveProject, clip_ref: tuple[int, int], effect_index: int, property_name: str) -> str | None:`
- **Behaviour:** reuse `_iter_clip_filters`; if `effect_index` out of range raise `IndexError` listing available count; scan children `<property name="X">` for match; return `.text or ""` if found, `None` if property absent. Do NOT raise on missing property — that is the `None` signal.

### Step 5: Implement `set_effect_property`
- **Signature:** `def set_effect_property(project: KdenliveProject, clip_ref: tuple[int, int], effect_index: int, property_name: str, value: str) -> None:`
- **Behaviour:** find the filter element via helper; if the `<property name>` child exists, replace its `.text`; else append a new `ET.SubElement`. Then `ET.tostring(root, encoding="unicode")` and replace the `xml_string` on the corresponding `OpaqueElement`. Log via module `logger` following existing patcher style (e.g., `logger.info("set_effect_property: ...")`).

### Step 6: Run tests green
- **Run:** `uv run pytest tests/unit/test_patcher_effect_properties.py -v`
- **Expected:** PASS.

### Step 7: Confirm no regressions
- **Run:** `uv run pytest tests/ -v`
- **Expected:** all prior tests still pass. If any parser/serializer round-trip test now fails, investigate — the changes must be purely additive.

### Step 8: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py tests/unit/test_patcher_effect_properties.py`
- **Message:** `feat: patcher effect-property extensions`

## Acceptance Criteria

- `[STRUCTURAL]` `patcher.py` exports `get_effect_property(clip_ref, effect_index, property_name) -> str | None`.
- `[STRUCTURAL]` `patcher.py` exports `set_effect_property(clip_ref, effect_index, property_name, value: str) -> None`.
- `[STRUCTURAL]` `patcher.py` exports `list_effects(clip_ref) -> list[dict]` where each dict has keys `index`, `mlt_service`, `kdenlive_id`, `properties` (dict).
- `[BEHAVIORAL]` `get_effect_property((2,0), 0, "rect")` on a fixture with a transform filter returns the existing rect string.
- `[BEHAVIORAL]` `set_effect_property((2,0), 0, "rect", "...")` mutates the in-memory project tree; subsequent `get_effect_property` returns the new string.
- `[BEHAVIORAL]` `list_effects((2,0))` returns filters in stack order.
- `[BEHAVIORAL]` `get_effect_property` on a non-existent property returns `None`; on a non-existent effect_index or clip raises `IndexError` with clear message.
- `[MECHANICAL]` `uv run pytest tests/unit/test_patcher_effect_properties.py -v` passes.

## Completeness Checklist

### `list_effects` return-dict fields

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `index` | `int` | required | `effect_find.find` (Sub-Spec 3), MCP error messages (Sub-Spec 4) |
| `mlt_service` | `str` | required (may be `""`) | `effect_find.find` service-name fallback |
| `kdenlive_id` | `str` | required (may be `""`) | `effect_find.find` primary key |
| `properties` | `dict[str, str]` | required | MCP tool diagnostic output |

### Resource / boundary limits
- Filter-stack enumeration: unbounded, linear scan of `project.opaque_elements`.
- No caching introduced (per Must-Nots).

## Verification Commands

- **Build:** not configured (pure Python; no build step).
- **Tests:** `uv run pytest tests/ -v`
- **Acceptance:**
  - `uv run pytest tests/unit/test_patcher_effect_properties.py -v` — covers all behavioural criteria.
  - `uv run pytest tests/unit/test_kdenlive_model.py tests/unit/test_kdenlive_parser.py tests/unit/test_kdenlive_writer.py tests/integration/test_kdenlive_roundtrip.py -v` — regression guard for parser/serializer.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:691-742` — `_apply_add_effect` shows exactly how filter XML is produced (attributes `track`, `clip_index`, child `<property>` nodes). The parse logic in the new helpers must accept this shape verbatim.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py:208-213` — `_find_playlist` style for small helpers.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/parser.py:41` — `_elem_to_opaque` for ET round-trip idioms.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` | Modify | Append three new module-level functions plus one helper. |
| `tests/unit/test_patcher_effect_properties.py` | Create | Unit tests for the new functions. |
