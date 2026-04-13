# Effect Stack Presets for Kdenlive MCP

## Meta
- Client: ForgeFrame (self)
- Project: Workshop Video Brain
- Repo: /home/caleb/Projects/ForgeFrame
- Date: 2026-04-13
- Author: Caleb Bennett
- Status: completed
- Executed: 2026-04-13
- Result: 3/3 sub-specs passed (2465 tests, 0 regressions, +58 new)
- Design Doc: `docs/plans/2026-04-13-stack-presets-design.md`
- Depends on shipped: Spec 1 (Keyframes), Spec 2 (Stack Ops), Spec 3 (Catalog)
- Quality Scores (7 dims / 35): Outcome 5 · Scope 5 · Decisions 5 · Edges 4 · Criteria 4 · Decomposition 4 · Purpose 5 · **Total 32/35**

## Outcome
Four MCP tools enable named, reusable effect-stack recipes. `effect_stack_preset` serializes a clip's filter stack to a YAML file in the workspace (`<workspace>/stacks/<name>.yaml`), validating against the effect catalog. `effect_stack_apply` loads by name (workspace → vault fallback) and applies to any target clip with `append`/`prepend`/`replace` mode. `effect_stack_promote` copies a workspace preset to the vault with an auto-generated markdown body. `effect_stack_list` enumerates presets across both tiers.

## Intent
**Trade-off hierarchy:**
1. Stack traveling with video project (workspace-first storage) over cross-project reusability (vault promotion is explicit)
2. Strict catalog validation at save time over permissive recovery
3. Compose primitives from Specs 1-3 — no new patcher or pipeline primitives
4. Tool-only authorship; human edits only the vault markdown body

**Preferences:**
- Prefer Pydantic for preset schema (matches existing workspace model patterns)
- Prefer YAML for both tiers over JSON
- Prefer explicit `mode` override on apply over magic defaults

**Escalation triggers:**
- If workspace manifest does not have a `vault_note_path` field and one cannot be derived, skip the wikilink silently (not an error).
- If vault root resolution cannot find a valid vault AND a vault-scoped operation is called — `_err`, do not guess a path.
- Any catalog validation failure during save — `_err`, do not attempt to save a partial preset.

## Context
Specs 1-3 shipped (commits `2bb76d6`, `ef9f0a6`, `1b82240`). Available primitives:
- `patcher.{get,set}_effect_property`, `list_effects`, `_iter_clip_filters`, `insert_effect_xml`, `remove_effect`, `reorder_effects`
- `pipelines.stack_ops.{serialize_stack, apply_paste, reorder_stack}` (keyframe-byte-exact preservation)
- `pipelines.effect_catalog.{CATALOG, find_by_name, find_by_service}` (321 effects)
- `workspace.create_snapshot` → `SnapshotRecord.snapshot_id`
- `WorkspaceManifest` has `vault_note_path` field

This spec is pure composition. No changes to `patcher.py` or existing pipelines.

Discussion: `EFFECTS_DISCUSSION.md` (repo root). Design doc: `docs/plans/2026-04-13-stack-presets-design.md`.

Key files touched:
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` (new)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended — 4 new MCP tools)
- `forge-project.json` (extended — optional `vault_root` field)

## Requirements

1. Preset data model is a Pydantic v2 `BaseModel` (`Preset`, `PresetEffect`, `ApplyHints`) with validation.
2. `effect_stack_preset` serializes a clip's filter stack to YAML at `<workspace>/stacks/<name>.yaml`. Validates every effect's `mlt_service` against the catalog; rejects presets with unknown services.
3. `effect_stack_apply` loads by name with workspace → vault fallback; applies with `mode` (override) or preset's `apply_hints.stack_order` (default).
4. `effect_stack_promote` copies workspace preset to `<vault>/patterns/effect-stacks/<name>.md` with auto-generated markdown body including wikilink to source video note if `workspace.vault_note_path` is set.
5. `effect_stack_list` enumerates presets across `workspace` / `vault` / `all` scopes.
6. Apply honors `apply_hints.stack_order` (unless overridden by `mode` param) and `apply_hints.blend_mode` (emitted as response hint for caller). `required_producers` and `track_placement` are surfaced in response as metadata only.
7. Keyframe animation strings preserved byte-exact through save → load → apply cycle (via Spec 2's regex-scoped attribute rewriting).
8. Apply auto-snapshots per existing policy and returns `snapshot_id`.
9. Vault root resolution: `forge-project.json.vault_root` → `~/.claude/forge.json.personal_vault` → fail for vault-scoped ops only.
10. Full test suite passes with zero regressions.

## Sub-Specs

### Sub-Spec 1: Preset Data Model + Storage I/O
**Scope.** Define Pydantic `Preset` model family. Implement save/load/list with two-tier storage. No catalog validation yet (Sub-Spec 2).

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` (new, initial)
- `tests/unit/test_stack_presets_io.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` Module exports `Preset`, `PresetEffect`, `ApplyHints` (Pydantic BaseModels), `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root`.
- `[STRUCTURAL]` `Preset` fields: `name: str`, `version: int = 1`, `created_at: datetime`, `updated_at: datetime`, `created_by: str`, `tags: tuple[str, ...] = ()`, `description: str = ""`, `source: dict | None = None`, `effects: tuple[PresetEffect, ...]`, `apply_hints: ApplyHints = ApplyHints()`.
- `[STRUCTURAL]` `PresetEffect` fields: `mlt_service: str`, `kdenlive_id: str = ""`, `xml: str`.
- `[STRUCTURAL]` `ApplyHints` fields: `blend_mode: str | None = None`, `stack_order: Literal["append","prepend","replace"] = "append"`, `track_placement: str | None = None`, `required_producers: tuple[str, ...] = ()`.
- `[BEHAVIORAL]` `save_preset(preset, workspace_root, scope="workspace")` writes YAML to `<workspace_root>/stacks/<preset.name>.yaml`; creates `stacks/` dir if absent.
- `[BEHAVIORAL]` `save_preset(preset, workspace_root=None, vault_root=..., scope="vault")` writes markdown with YAML frontmatter + auto-generated body to `<vault_root>/patterns/effect-stacks/<preset.name>.md`.
- `[BEHAVIORAL]` `load_preset(name, workspace_root, vault_root)` prefers workspace; falls back to vault. Returns validated `Preset`.
- `[BEHAVIORAL]` `load_preset` with missing name in both tiers raises `FileNotFoundError` listing both searched paths.
- `[BEHAVIORAL]` `list_presets(workspace_root, vault_root, scope="all")` enumerates both tiers; returns list of dicts `{name, scope, tags, effect_count, description, path}`. Malformed files are skipped and included as `{skipped: [{path, error}]}` in a secondary field.
- `[BEHAVIORAL]` `resolve_vault_root(project_json_path, forge_config_path) -> Path | None` returns the first of `forge-project.json.vault_root`, `~/.claude/forge.json.personal_vault`, or `None`.
- `[BEHAVIORAL]` YAML round-trip: saving a preset then loading returns byte-identical data (effects `xml` strings preserved exactly).
- `[BEHAVIORAL]` Vault markdown: frontmatter is valid YAML; body contains name header, description, tags line, effect table, "Referenced from" wikilink when `source_video_note_path` is provided (omitted otherwise).
- `[MECHANICAL]` `uv run pytest tests/unit/test_stack_presets_io.py -v` passes.

**Dependencies.** none

---

### Sub-Spec 2: Preset Operations Pipeline (Serialize, Validate, Apply, Promote)
**Scope.** Implement the preset operations that compose Spec 2 (stack ops) and Spec 3 (catalog). Purely pipeline — no MCP.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` (extended)
- `tests/unit/test_stack_presets_ops.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` Module exports `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault`, `render_vault_body`.
- `[STRUCTURAL]` `serialize_clip_to_preset(project, clip_ref, name, description="", tags=(), created_by="effect_stack_preset") -> Preset` builds a fresh `Preset` from a live clip via `stack_ops.serialize_stack`.
- `[STRUCTURAL]` `validate_against_catalog(preset, strict=True) -> list[str]` returns a list of warning/error messages (empty = all effects found); with `strict=True` raises `ValueError` on unknown `mlt_service` rather than returning.
- `[STRUCTURAL]` `apply_preset(project, target_clip_ref, preset, mode_override=None) -> dict` returns `{"effects_applied": int, "mode": str, "blend_mode_hint": str|None, "track_placement_hint": str|None, "required_producers_hint": tuple[str, ...]}`.
- `[STRUCTURAL]` `promote_to_vault(name, workspace_root, vault_root, source_video_note_path=None) -> Path` copies and renders markdown.
- `[BEHAVIORAL]` `serialize_clip_to_preset` against a clip with 3 filters produces a `Preset` with 3 `PresetEffect`s whose `xml` fields equal the source `OpaqueElement.xml_string`s byte-for-byte.
- `[BEHAVIORAL]` `validate_against_catalog` on a preset with all catalog-known services returns `[]`.
- `[BEHAVIORAL]` `validate_against_catalog(strict=True)` on a preset with an unknown `mlt_service` raises `ValueError` whose message names the offending service and suggests checking `effect_list_common`.
- `[BEHAVIORAL]` `apply_preset` with `mode_override=None` uses `preset.apply_hints.stack_order`; with `mode_override="replace"` overrides.
- `[BEHAVIORAL]` `apply_preset` writes the correct number of filters to the target clip (verified via `patcher.list_effects`).
- `[BEHAVIORAL]` `apply_preset` preserves keyframe animation strings byte-exact (copy keyframed rect, apply to different clip, assert re-parsed `rect` property equals source).
- `[BEHAVIORAL]` `apply_preset` response surfaces `blend_mode_hint`, `track_placement_hint`, `required_producers_hint` verbatim from `preset.apply_hints` without acting on them.
- `[BEHAVIORAL]` `promote_to_vault` with `source_video_note_path=Path("Videos/My Video.md")` embeds `[[My Video]]` wikilink in the rendered body.
- `[BEHAVIORAL]` `promote_to_vault` with `source_video_note_path=None` omits the "Referenced from" line.
- `[BEHAVIORAL]` `promote_to_vault` with missing workspace preset raises `FileNotFoundError`.
- `[MECHANICAL]` `uv run pytest tests/unit/test_stack_presets_ops.py -v` passes.

**Dependencies.** sub-spec 1, Spec 2 (stack_ops), Spec 3 (effect_catalog)

---

### Sub-Spec 3: MCP Tool Surface + Integration
**Scope.** Register four MCP tools and wire them to the pipeline.

**Files.**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (extended)
- `tests/integration/test_stack_presets_mcp_tools.py` (new)

**Acceptance Criteria.**
- `[STRUCTURAL]` `server/tools.py` registers `effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote`, `effect_stack_list`.
- `[STRUCTURAL]` `effect_stack_preset(workspace_path, project_file, track, clip, name, description="", tags: str = "", apply_hints: str = "") -> dict` accepts `tags` and `apply_hints` as JSON-encoded strings per MCP string-only convention. Returns `{"status","data":{"path":str,"effect_count":int,"scope":"workspace"}}`.
- `[STRUCTURAL]` `effect_stack_apply(workspace_path, project_file, track, clip, name, mode: str = "") -> dict` — `mode=""` means "use preset's `apply_hints.stack_order`". Returns `{"status","data":{"effects_applied":int,"mode":str,"snapshot_id":str,"blend_mode_hint":str|None,"track_placement_hint":str|None,"required_producers_hint":[...]}}`.
- `[STRUCTURAL]` `effect_stack_promote(workspace_path, name) -> dict` returns `{"status","data":{"workspace_path":str,"vault_path":str}}`.
- `[STRUCTURAL]` `effect_stack_list(workspace_path, scope: str = "all") -> dict` returns `{"status","data":{"presets":[...],"skipped":[...]}}`.
- `[INTEGRATION]` All four tools are importable as callables from `workshop_video_brain.edit_mcp.server.tools` after module import.
- `[BEHAVIORAL]` Against fixture `keyframe_project.kdenlive`: `effect_stack_preset(track=2, clip=0, name="test-preset")` writes `<ws>/stacks/test-preset.yaml`; file exists with valid YAML parsing back to a `Preset` with `effect_count >= 1`.
- `[BEHAVIORAL]` `effect_stack_preset` with a clip whose filter has `mlt_service="nonexistent.service"` returns `_err` naming the service.
- `[BEHAVIORAL]` End-to-end: `effect_stack_preset(source)` → `effect_stack_apply(target, name="test-preset")` → `patcher.list_effects(target)` shows the correct filter count; re-parsing the project preserves keyframe strings byte-exact.
- `[BEHAVIORAL]` `effect_stack_apply` with `mode="replace"` overrides preset's `stack_order`.
- `[BEHAVIORAL]` `effect_stack_apply` with a name not found in workspace or vault returns `_err` listing both searched paths.
- `[BEHAVIORAL]` `effect_stack_apply` response includes `blend_mode_hint`, `track_placement_hint`, `required_producers_hint` verbatim from the preset.
- `[BEHAVIORAL]` Each write-mutating call (preset, apply, promote) produces a `snapshot_id` on disk when it mutates the project. (Preset save does NOT mutate the project — no snapshot for preset or promote; only apply snapshots.)
- `[BEHAVIORAL]` `effect_stack_promote` with workspace manifest `vault_note_path` set to "Videos/My Vid.md" embeds `[[My Vid]]` in the rendered markdown.
- `[BEHAVIORAL]` `effect_stack_promote` when vault root is not configured returns `_err("Vault root not configured — set vault_root in forge-project.json or personal_vault in ~/.claude/forge.json")`.
- `[BEHAVIORAL]` `effect_stack_list(scope="all")` returns presets from both tiers with scope labels.
- `[MECHANICAL]` `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v` passes.
- `[MECHANICAL]` `uv run pytest tests/ -v` (full suite) passes with no regressions.

**Dependencies.** sub-spec 1, sub-spec 2

## Edge Cases

- **Save preset with name containing path separators** (`my/preset`) → slugify to `my-preset` before write; warn in response.
- **Save with empty effects list** (clip has no filters) → succeed with `effect_count: 0`; warn that apply will be a no-op.
- **Apply to clip with existing keyframes on filters being replaced** (mode="replace") → keyframes lost by design; this is what replace means.
- **Preset with `apply_hints.stack_order` not in the Literal set** (corrupt file, hand-edited) → Pydantic `ValidationError` on load; wrap in `_err`.
- **List with both tiers empty** → returns `{"presets": [], "skipped": []}`.
- **List with a workspace preset and a vault preset sharing a name** → both appear in `scope="all"`; workspace wins on `scope="workspace"` lookup.
- **Promote with no source video note in workspace** → wikilink omitted; rest of body unchanged.
- **Promote overwrites existing vault file** — by design, no warning (tool-only writes).
- **Vault root path has spaces or is a relative path** → resolve to absolute via `Path(...).expanduser().resolve()`.
- **YAML file with unknown extra fields** (forward-compat for future spec expansion) → Pydantic config `extra="ignore"` to preserve compatibility.

## Out of Scope

- Preset search/filter by tags or description (Spec 7+ enhancement)
- Preset versioning migrations (breaking schema changes trigger `version` bump; migration logic is future work)
- Preset composition (combining multiple presets) — explicit future work
- Cross-project preset sharing outside the single-vault model
- GUI preset browser
- Automatic vault note linking during `effect_stack_preset` save (only `promote` does wikilinks)

## Constraints

### Musts
- All acceptance criteria.
- Python 3.12+.
- Pydantic v2 for the preset model.
- Use YAML (PyYAML) for serialization.
- Reuse `stack_ops.serialize_stack` / `apply_paste` for clip↔stack conversion — do NOT re-implement XML handling.
- Reuse `effect_catalog.find_by_service` for catalog validation.
- Auto-snapshot on `effect_stack_apply` only (the only tool that mutates the project).

### Must-Nots
- Must NOT modify `patcher.py` or existing Spec 1/2/3 public APIs.
- Must NOT write to `media/raw/` or `projects/source/`.
- Must NOT break keyframe byte-exactness through save → load → apply.
- Must NOT require vault configuration for workspace-scoped operations.

### Preferences
- Prefer strict catalog validation with clear error messages.
- Prefer Pydantic `validate_assignment=True` so mutations re-validate.
- Prefer JSON-encoded strings for complex MCP tool params (`tags`, `apply_hints`) — matches existing keyframe-tool convention.

### Escalation Triggers
- If `WorkspaceManifest` doesn't expose `vault_note_path` field, stop and ask.
- If `PyYAML` is not already a project dependency, confirm before adding it.
- If catalog lookup by `mlt_service` is too slow for bulk validation, ask (would need an index).

## Verification

1. `uv run pytest tests/ -v` passes (baseline 2407 + new tests).
2. Save a preset from a real workspace clip; inspect `<workspace>/stacks/<name>.yaml` for readability.
3. Apply the preset to a fresh clip; confirm via Kdenlive 25.x UI that filters render correctly and animations play.
4. Promote the preset to the vault; open the resulting `.md` in Obsidian; confirm frontmatter parses and body renders.
5. Change a filter's mlt_service to something fake, re-save — confirm `effect_stack_preset` rejects.
6. List presets with scope="all" from a workspace that has 2 local + vault that has 3 — expect 5 entries with correct scope labels.
