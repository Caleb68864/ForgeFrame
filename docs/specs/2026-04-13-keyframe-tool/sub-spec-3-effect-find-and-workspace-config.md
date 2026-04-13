---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-keyframe-tool.md"
sub_spec_number: 3
title: "Effect-Find Module + Workspace Config Extension"
date: 2026-04-13
dependencies: [none]
---

# Sub-Spec 3: Effect-Find Module + Workspace Config Extension

Refined from spec.md — ForgeFrame keyframe tool.

## Scope

Two independent, small additions:

1. **`pipelines/effect_find.py`** — a `find(project, clip_ref, name) -> int`
   helper that resolves a filter within a clip's filter stack by
   `kdenlive_id` (preferred) or `mlt_service` (fallback). Reuses the
   `_iter_clip_filters` helper produced by Sub-Spec 1 rather than re-parsing
   `OpaqueElement` XML strings.

2. **Workspace model extension** — add a typed `keyframe_defaults` Pydantic
   sub-model on `Workspace` (or a structured `config["keyframe_defaults"]`
   readable via a property). Field `ease_family: Literal["sine","quad",
   "cubic","quart","quint","expo","circ","back","elastic","bounce"]`, default
   `"cubic"`. Loader reads it from `workspace.yaml` if present; invalid values
   fail fast at load time (per master-spec Edge Cases).

**Codebase note.** The current `Workspace` model
(`core/models/workspace.py:13`) stores arbitrary config as a loose
`config: dict`. The loader path is `WorkspaceManager.open()` /
`WorkspaceManager.create()` (`workspace/manager.py`). Worker must inspect
`manager.py` to determine whether to (a) add a new `keyframe_defaults` field
to `Workspace` directly and round-trip it through the manager, or (b) add a
typed view `workspace.keyframe_defaults` computed from `config["keyframe_defaults"]`.
Preference: option (a) — first-class Pydantic field — matching the master
spec's "Prefer Pydantic for new data models" constraint. If manager.py
serialization cannot accommodate new top-level fields without schema
migration, fall back to option (b) and note the decision in the commit
message.

## Interface Contracts

### Provides
- `effect_find.find(project, clip_ref: tuple[int,int], name: str) -> int` — returns filter index within the clip's filter stack.
- `Workspace.keyframe_defaults.ease_family: str` (one of the 10 families), default `"cubic"`.
- Workspace load-time validation for invalid `ease_family` values.

### Requires
- Ideally: `_iter_clip_filters` from Sub-Spec 1 (to avoid duplicating XML parsing). If Sub-Spec 1 is not yet merged when this sub-spec is run, duplicate a minimal local parser and mark with `# TODO: replace with patcher._iter_clip_filters once merged`.
- `VALID_EASE_FAMILIES` from Sub-Spec 2 for the `Literal` type validation (import path: `workshop_video_brain.edit_mcp.pipelines.keyframes.VALID_EASE_FAMILIES`). If Sub-Spec 2 is not yet merged, inline the 10-family tuple and mark with a TODO.

### Shared State
- `workspace.yaml` gains a new nested key. Legacy workspaces missing the key MUST load without error (yield default `cubic`).

## Implementation Steps

### Step 1: Write failing tests
- **Files:**
  - `tests/unit/test_effect_find.py` — covers filter lookup.
  - `tests/unit/test_workspace_keyframe_defaults.py` — covers workspace loader.
- **Tests (effect_find):**
  - `test_find_by_kdenlive_id`
  - `test_find_falls_back_to_mlt_service`
  - `test_find_raises_lookup_error_with_available_effects_listed`
  - `test_find_raises_value_error_when_ambiguous_with_indices_listed`
  - `test_find_prefers_kdenlive_id_over_mlt_service`
- **Tests (workspace):**
  - `test_loads_ease_family_from_yaml`
  - `test_missing_keyframe_defaults_yields_cubic`
  - `test_invalid_ease_family_raises_validation_error`
  - `test_roundtrip_ease_family_through_save_load`
- **Run:** `uv run pytest tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py -v`
- **Expected:** all fail.

### Step 2: Implement `effect_find.find`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_find.py` (create).
- **Pattern:** follow `pipelines/effect_apply.py` header style.
- **Implementation:**
  ```python
  def find(project: KdenliveProject, clip_ref: tuple[int, int], name: str) -> int:
      """Resolve an effect index on a clip by kdenlive_id (preferred) or mlt_service.

      Raises LookupError when no match; ValueError when ambiguous (>=2 matches).
      """
      # 1. Call patcher.list_effects(project, clip_ref) to get ordered stack.
      # 2. Collect indices where entry["kdenlive_id"] == name.
      # 3. If zero, collect indices where entry["mlt_service"] == name.
      # 4. Zero matches → LookupError listing all available effects:
      #    f"No effect named '{name}'. Available: [{index=0, kdenlive_id='...', mlt_service='...'}, ...]"
      # 5. >= 2 matches → ValueError listing indices and suggesting effect_index= usage.
      # 6. Exactly 1 → return int.
  ```
- Import `list_effects` from `workshop_video_brain.edit_mcp.adapters.kdenlive.patcher` (Sub-Spec 1 dependency).

### Step 3: Extend `Workspace` model
- **File:** `workshop-video-brain/src/workshop_video_brain/core/models/workspace.py`.
- **Action:** modify.
- **Changes:**
  - Add new model:
    ```python
    class KeyframeDefaults(SerializableMixin):
        ease_family: Literal["sine","quad","cubic","quart","quint",
                             "expo","circ","back","elastic","bounce"] = "cubic"
    ```
  - Add field on `Workspace`:
    ```python
    keyframe_defaults: KeyframeDefaults = Field(default_factory=KeyframeDefaults)
    ```
- **Import:** `from typing import Literal`.
- **Guard:** do NOT remove the existing `config: dict` field — legacy data must still round-trip.

### Step 4: Adjust workspace loader
- **File:** `workshop-video-brain/src/workshop_video_brain/workspace/manager.py`.
- **Action:** modify — ensure `WorkspaceManager.open()` deserializes `keyframe_defaults` from `workspace.yaml`, and `WorkspaceManager.create()` / any save path serializes it.
- **Pattern:** inspect the existing YAML round-trip in `manager.py`; Pydantic's `model_validate` should handle the new field automatically if the YAML is passed through `model_validate`. If the manager currently hand-picks fields, extend that set.

### Step 5: Confirm the loader fails fast on invalid family
- Pydantic `Literal` validation already does this; assert the exception type in `test_invalid_ease_family_raises_validation_error` is `pydantic.ValidationError` (or the wrapper raised by the manager — match whatever `WorkspaceManager.open()` raises on other validation errors; inspect manager.py).

### Step 6: Run tests green
- **Run:** `uv run pytest tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py -v`
- **Expected:** PASS.

### Step 7: Full-suite regression check
- **Run:** `uv run pytest tests/ -v`
- **Expected:** no regressions. If any existing workspace round-trip test breaks due to the new field, the default-factory should have made the field optional; investigate.

### Step 8: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_find.py workshop-video-brain/src/workshop_video_brain/core/models/workspace.py workshop-video-brain/src/workshop_video_brain/workspace/manager.py tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py`
- **Message:** `feat: effect-find module and workspace keyframe_defaults`

## Acceptance Criteria

- `[STRUCTURAL]` `effect_find.py` exports `find(project, clip_ref, name: str) -> int`.
- `[STRUCTURAL]` `Workspace` model has typed `keyframe_defaults.ease_family` with `Literal` of the 10 families, default `"cubic"`.
- `[STRUCTURAL]` Loader reads the field from `workspace.yaml`; absence yields default.
- `[BEHAVIORAL]` `find(project, (2,0), "transform")` returns index of filter whose `kdenlive_id == "transform"`.
- `[BEHAVIORAL]` `find(project, (2,0), "affine")` falls back to `mlt_service`.
- `[BEHAVIORAL]` `find` raises `LookupError` listing all effects when no match.
- `[BEHAVIORAL]` `find` raises `ValueError` with all matching indices when ambiguous.
- `[BEHAVIORAL]` YAML `keyframe_defaults: {ease_family: "expo"}` → `workspace.keyframe_defaults.ease_family == "expo"`.
- `[BEHAVIORAL]` Missing section → `"cubic"`.
- `[BEHAVIORAL]` Invalid family value → validation error at load time.
- `[MECHANICAL]` `uv run pytest tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py -v` passes.

## Completeness Checklist

### `KeyframeDefaults` model fields

| Field | Type | Required | Used By |
|-------|------|----------|---------|
| `ease_family` | `Literal[10 families]` | optional (default `"cubic"`) | Sub-Spec 4 MCP tools (passed into `build_keyframe_string`) |

### Valid `ease_family` values (ALL must be accepted)

`sine`, `quad`, `cubic`, `quart`, `quint`, `expo`, `circ`, `back`, `elastic`, `bounce` — 10 total.

### `find` error-message content

- `LookupError`: MUST include full list of `[{index, kdenlive_id, mlt_service}]` for the clip.
- `ValueError` (ambiguous): MUST include the list of matching indices AND mention `effect_index=` as the disambiguation parameter.

## Verification Commands

- **Build:** not configured.
- **Tests:** `uv run pytest tests/unit/test_effect_find.py tests/unit/test_workspace_keyframe_defaults.py tests/ -v`
- **Acceptance:** above pytest command green = acceptance met.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/core/models/workspace.py:13` — existing `Workspace` model layout.
- `workshop-video-brain/src/workshop_video_brain/core/models/transitions.py` — reference for `Literal` + default Pydantic patterns.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py` — module header and error-type conventions.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_find.py` | Create | `find()` helper. |
| `workshop-video-brain/src/workshop_video_brain/core/models/workspace.py` | Modify | Add `KeyframeDefaults` submodel and field. |
| `workshop-video-brain/src/workshop_video_brain/workspace/manager.py` | Modify (likely) | Round-trip the new nested field through `workspace.yaml`. |
| `tests/unit/test_effect_find.py` | Create | `find()` unit tests. |
| `tests/unit/test_workspace_keyframe_defaults.py` | Create | Workspace loader tests. |
