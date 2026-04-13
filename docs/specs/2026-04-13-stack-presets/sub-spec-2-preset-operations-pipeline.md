---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-presets.md"
sub_spec_number: 2
title: "Preset Operations Pipeline (Serialize, Validate, Apply, Promote)"
date: 2026-04-13
dependencies: [1]
---

# Sub-Spec 2: Preset Operations Pipeline

Refined from `docs/specs/2026-04-13-stack-presets.md` — Stack Presets feature.

## Scope

Extend the `stack_presets` module from Sub-Spec 1 with operations that compose existing primitives:
- `serialize_clip_to_preset` — wraps `pipelines.stack_ops.serialize_stack` to produce a `Preset`.
- `validate_against_catalog` — checks every `PresetEffect.mlt_service` against `pipelines.effect_catalog.find_by_service`.
- `apply_preset` — wraps `pipelines.stack_ops.apply_paste` to write a preset's stack onto a target clip, honoring `apply_hints.stack_order` (or an override).
- `promote_to_vault` — copies a workspace preset to the vault, rendering an auto-generated markdown body (with optional wikilink to source video note).
- `render_vault_body` — pure function building the markdown body string.

Pure pipeline code — no MCP, no fastmcp imports. Sub-Spec 3 wires it to MCP tools.

## Interface Contracts

### Provides
- `serialize_clip_to_preset(project: KdenliveProject, clip_ref: tuple[int, int], name: str, *, description: str = "", tags: tuple[str, ...] = (), created_by: str = "effect_stack_preset", apply_hints: ApplyHints | None = None) -> Preset`
- `validate_against_catalog(preset: Preset, *, strict: bool = True) -> list[str]` — returns warning list; with `strict=True` raises `ValueError` on first unknown service.
- `apply_preset(project: KdenliveProject, target_clip_ref: tuple[int, int], preset: Preset, *, mode_override: Literal["append","prepend","replace"] | None = None) -> dict` — returns dict per spec.
- `promote_to_vault(name: str, workspace_root: Path, vault_root: Path, *, source_video_note_path: Path | None = None) -> Path`
- `render_vault_body(preset: Preset, *, source_video_note_path: Path | None = None) -> str`

### Requires
- From Sub-Spec 1: `Preset`, `PresetEffect`, `ApplyHints`, `save_preset`, `load_preset`.
- From `pipelines.stack_ops`: `serialize_stack`, `apply_paste`.
- From `pipelines.effect_catalog`: `find_by_service`.
- From `edit_mcp.adapters.kdenlive.patcher`: `list_effects` (test verification only — not called by pipeline itself).

### Shared State
- Mutates `KdenliveProject` instances passed to `apply_preset` (in-memory only — caller owns serialization).
- Reads workspace YAML / writes vault markdown for `promote_to_vault`.

## Implementation Steps

### Step 1: Write failing tests
- **File:** `tests/unit/test_stack_presets_ops.py` (new)
- **Tests:**
  - `test_module_exports_ops` — assert `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`, `render_vault_body` importable.
  - `test_serialize_clip_to_preset_field_count` — Parse fixture `tests/integration/fixtures/keyframe_project.kdenlive`. Locate a clip with at least 1 filter (track=2, clip=0 has the `transform` filter from Spec 1's fixture). `p = serialize_clip_to_preset(project, (2,0), name="test", description="d", tags=("a","b"))`. Assert `p.name == "test"`, `p.description == "d"`, `p.tags == ("a","b")`, `len(p.effects) == <count>`, each `effect.mlt_service` is non-empty.
  - `test_serialize_byte_exact_xml` — Compare each `p.effects[i].xml` to the underlying `OpaqueElement.xml_string` of the same filter (call `stack_ops.serialize_stack` directly to get the source dict, compare strings).
  - `test_validate_against_catalog_clean_returns_empty` — Build a `Preset` with `PresetEffect(mlt_service="frei0r.contrast0r", kdenlive_id="contrast0r", xml="<filter/>")` (a known catalog entry — verify via `find_by_service`). `validate_against_catalog(p, strict=True)` returns `[]`.
  - `test_validate_unknown_service_strict_raises` — `Preset` with `PresetEffect(mlt_service="not.real")`. `validate_against_catalog(p, strict=True)` raises `ValueError`. Message contains the string `"not.real"` and `"effect_list_common"`.
  - `test_validate_unknown_service_non_strict_returns_warnings` — Same; `strict=False` returns a list of length 1 whose message contains `"not.real"`.
  - `test_apply_preset_uses_hints_default_mode` — Build `Preset` with `apply_hints=ApplyHints(stack_order="prepend")` and 2 fake effects (use real XML strings copied from fixture). Apply to a clip with 1 existing filter. Result: `result["mode"] == "prepend"`. Verify via `patcher.list_effects(project, target)` length == 3 (2 prepended + 1 existing).
  - `test_apply_preset_mode_override` — Same preset; `apply_preset(..., mode_override="replace")`. `result["mode"] == "replace"`. Final filter count == 2 (existing dropped).
  - `test_apply_preset_returns_response_dict_keys` — Build preset with `apply_hints=ApplyHints(blend_mode="screen", track_placement="V2", required_producers=("audio",))`. Apply. Result has keys `effects_applied (int), mode (str), blend_mode_hint (str), track_placement_hint (str), required_producers_hint (tuple)`. Values verbatim.
  - `test_apply_preset_keyframes_byte_exact` — Build a preset by serializing a clip whose filter has keyframed `rect`. Apply preset to a different clip. Re-read the target clip's filter `rect` property via `patcher.get_effect_property`. Assert byte-identical with source `rect` string.
  - `test_promote_to_vault_creates_markdown` — Save a preset to workspace via `save_preset`. `promote_to_vault(name, workspace_root, vault_root, source_video_note_path=None)`. Assert returned path is `vault_root/patterns/effect-stacks/<name>.md`. File exists; content has frontmatter and body.
  - `test_promote_to_vault_wikilink_embedded` — `promote_to_vault(..., source_video_note_path=Path("Videos/My Video.md"))`. Read result file. Body contains `[[My Video]]` and the literal text `Referenced from`.
  - `test_promote_to_vault_no_wikilink_when_none` — Same call with `source_video_note_path=None`. Body does NOT contain `Referenced from`.
  - `test_promote_to_vault_missing_workspace_raises` — `promote_to_vault("nope", workspace_root, vault_root)` raises `FileNotFoundError`.
  - `test_render_vault_body_contains_effect_table` — `render_vault_body(preset)` includes a markdown table with one row per effect, columns include `mlt_service` and `kdenlive_id`.
- **Run:** `uv run pytest tests/unit/test_stack_presets_ops.py -v`
- **Expected:** FAIL.

### Step 2: Implement `serialize_clip_to_preset`
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` (extend)
- **Action:**
  ```python
  from workshop_video_brain.edit_mcp.pipelines import stack_ops
  def serialize_clip_to_preset(project, clip_ref, name, *, description="", tags=(), created_by="effect_stack_preset", apply_hints=None):
      stack = stack_ops.serialize_stack(project, clip_ref)
      effects = tuple(
          PresetEffect(
              mlt_service=e["mlt_service"],
              kdenlive_id=e.get("kdenlive_id", ""),
              xml=e["xml"],
          )
          for e in stack["effects"]
      )
      return Preset(
          name=name,
          description=description,
          tags=tuple(tags),
          created_by=created_by,
          source={"track": clip_ref[0], "clip": clip_ref[1]},
          effects=effects,
          apply_hints=apply_hints or ApplyHints(),
      )
  ```

### Step 3: Implement `validate_against_catalog`
- **Action:**
  ```python
  from workshop_video_brain.edit_mcp.pipelines import effect_catalog
  def validate_against_catalog(preset, *, strict=True):
      warnings = []
      for i, eff in enumerate(preset.effects):
          if effect_catalog.find_by_service(eff.mlt_service) is None:
              msg = (f"effects[{i}].mlt_service={eff.mlt_service!r} not found in catalog "
                     f"(check effect_list_common for valid services)")
              if strict:
                  raise ValueError(msg)
              warnings.append(msg)
      return warnings
  ```

### Step 4: Implement `apply_preset`
- **Action:** Translate preset back to a `stack_dict` shape that `stack_ops.apply_paste` accepts (it expects `{"effects": [{"xml": ...}, ...]}`). Choose mode from `mode_override or preset.apply_hints.stack_order`. Return the response dict.
  ```python
  def apply_preset(project, target_clip_ref, preset, *, mode_override=None):
      mode = mode_override or preset.apply_hints.stack_order
      stack_dict = {"effects": [{"xml": e.xml} for e in preset.effects]}
      n = stack_ops.apply_paste(project, target_clip_ref, stack_dict, mode=mode)
      return {
          "effects_applied": n,
          "mode": mode,
          "blend_mode_hint": preset.apply_hints.blend_mode,
          "track_placement_hint": preset.apply_hints.track_placement,
          "required_producers_hint": preset.apply_hints.required_producers,
      }
  ```

### Step 5: Implement `render_vault_body` and `promote_to_vault`
- **Action:** `render_vault_body(preset, source_video_note_path=None)` returns a markdown string:
  ```
  # {preset.name}
  
  {preset.description}
  
  **Tags:** {', '.join(preset.tags) or '_none_'}
  
  ## Effects
  
  | # | mlt_service | kdenlive_id |
  |---|-------------|-------------|
  | 0 | ... | ... |
  
  Referenced from [[{stem}]]   <-- only if source_video_note_path provided
  ```
  - `promote_to_vault(name, workspace_root, vault_root, source_video_note_path=None)`: load preset from workspace (via `load_preset(name, workspace_root, vault_root=None)` — workspace-only). Build body via `render_vault_body`. Call `save_preset(preset, vault_root=vault_root, scope="vault", body_renderer=lambda p: render_vault_body(p, source_video_note_path=source_video_note_path))`. Return resulting path.

### Step 6: Verify tests pass
- **Run:** `uv run pytest tests/unit/test_stack_presets_ops.py -v`
- **Expected:** PASS.

### Step 7: Run full suite
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS.

### Step 8: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py tests/unit/test_stack_presets_ops.py`
- **Message:** `feat: preset operations pipeline (serialize, validate, apply, promote)`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`, `render_vault_body`.
- `[STRUCTURAL]` `serialize_clip_to_preset` signature matches spec.
- `[STRUCTURAL]` `validate_against_catalog(preset, strict=True) -> list[str]` returns warnings; with `strict=True` raises on unknown service.
- `[STRUCTURAL]` `apply_preset` returns `{"effects_applied", "mode", "blend_mode_hint", "track_placement_hint", "required_producers_hint"}`.
- `[STRUCTURAL]` `promote_to_vault(name, workspace_root, vault_root, source_video_note_path=None) -> Path`.
- `[BEHAVIORAL]` `serialize_clip_to_preset` produces byte-exact `xml` per effect.
- `[BEHAVIORAL]` `validate_against_catalog` empty list when all clean.
- `[BEHAVIORAL]` `validate_against_catalog(strict=True)` raises with message naming offending service + `effect_list_common`.
- `[BEHAVIORAL]` `apply_preset` mode_override overrides hints.
- `[BEHAVIORAL]` `apply_preset` writes correct count; verified via `patcher.list_effects`.
- `[BEHAVIORAL]` Keyframe strings byte-exact through serialize → apply.
- `[BEHAVIORAL]` `apply_preset` surfaces hints verbatim.
- `[BEHAVIORAL]` `promote_to_vault` with note path embeds `[[stem]]` wikilink.
- `[BEHAVIORAL]` `promote_to_vault` with `None` omits the line.
- `[BEHAVIORAL]` `promote_to_vault` missing workspace preset raises `FileNotFoundError`.
- `[MECHANICAL]` `uv run pytest tests/unit/test_stack_presets_ops.py -v` passes.

## Completeness Checklist

### `apply_preset` response dict
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| effects_applied | int | required | MCP tool response |
| mode | str ("append"/"prepend"/"replace") | required | MCP tool response |
| blend_mode_hint | str \| None | required (None ok) | caller hint |
| track_placement_hint | str \| None | required (None ok) | caller hint |
| required_producers_hint | tuple[str, ...] | required (() ok) | caller hint |

### Vault markdown body sections
- H1 header with preset name — required
- Description paragraph — required (empty string allowed)
- Tags line — required (rendered as `_none_` when empty)
- Effects table — required, columns `# | mlt_service | kdenlive_id`
- "Referenced from [[stem]]" line — included iff `source_video_note_path` provided

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_stack_presets_ops.py -v`
- **Full suite:** `uv run pytest tests/ -v`
- **Acceptance:** Each acceptance criterion has a corresponding test in Step 1.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` — module style; reuse `serialize_stack` / `apply_paste` directly. Do NOT re-implement XML rewriting.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` — `find_by_service` returns `EffectDef | None`; check for `None`.
- `tests/integration/fixtures/keyframe_project.kdenlive` — re-use as the canonical filter-bearing fixture (Spec 1 already provides it; do NOT add new fixtures).

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` | Modify | Append ops functions |
| `tests/unit/test_stack_presets_ops.py` | Create | Pipeline ops tests |
