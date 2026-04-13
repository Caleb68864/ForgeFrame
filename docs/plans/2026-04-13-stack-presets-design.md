---
date: 2026-04-13
topic: "Effect stack presets for Kdenlive MCP"
author: Caleb Bennett
status: draft
tags:
  - design
  - stack-presets
  - kdenlive
  - mcp
---

# Effect Stack Presets — Design

## Summary
Named, reusable effect-stack recipes saved as YAML files. Two-tier storage: workspace-local by default (travels with the video project), promotable to the vault for cross-project reuse. Strict catalog validation on save catches typos early. Apply honors `blend_mode` and `stack_order` hints; surfaces `required_producers` and `track_placement` as metadata for the caller to act on. Four MCP tools: `effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote`, `effect_stack_list`.

## Approach Selected
**Two-tier YAML storage + strict catalog validation on save + mode-aware apply.** Reuses catalog (Spec 3) for validation, stack-ops pipeline (Spec 2) for the actual clip mutation, and keyframe preservation (Spec 1). No new primitives in `patcher.py` — this spec is entirely composition.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ MCP surface (server/tools.py)                                │
│  effect_stack_preset · effect_stack_apply                    │
│  effect_stack_promote · effect_stack_list                    │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ pipelines/stack_presets.py (new)                             │
│  - Preset dataclass (validated via pydantic)                 │
│  - save_preset(preset, scope: "workspace"|"vault")           │
│  - load_preset(name, workspace, vault) — w → v fallback      │
│  - list_presets(scope)                                       │
│  - serialize_clip_to_preset(project, clip_ref, name, tags)   │
│  - validate_against_catalog(preset)                          │
│  - apply_preset(project, clip_ref, preset, mode)             │
│  - promote_to_vault(name, workspace, vault)                  │
│  - render_vault_body(preset) — markdown template             │
└──────────────────────────────────────────────────────────────┘
         │                              │
         │                              │
         ▼                              ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│ pipelines/stack_ops  │    │ pipelines/effect_catalog     │
│  serialize_stack     │    │ find_by_name / find_by_      │
│  apply_paste         │    │ service / ParamType          │
│ (Spec 2)             │    │ (Spec 3)                     │
└──────────────────────┘    └──────────────────────────────┘
```

## Components

### `pipelines/stack_presets.py` (new)

**Data model** (Pydantic):
```python
class PresetEffect(BaseModel):
    mlt_service: str       # primary identifier
    kdenlive_id: str = ""  # echoed for reference
    xml: str               # raw OpaqueElement.xml_string (includes all properties + keyframes)

class ApplyHints(BaseModel):
    blend_mode: str | None = None         # honored on apply
    stack_order: Literal["append","prepend","replace"] = "append"  # honored
    track_placement: str | None = None    # metadata only (surfaced in response)
    required_producers: tuple[str, ...] = () # metadata only

class Preset(BaseModel):
    name: str
    version: int = 1
    created_at: datetime
    updated_at: datetime
    created_by: str         # tool name that wrote it
    tags: tuple[str, ...] = ()
    description: str = ""
    source: dict | None = None  # {"workspace": ..., "clip_ref": [t, c]}
    effects: tuple[PresetEffect, ...]
    apply_hints: ApplyHints = ApplyHints()
```

**Functions:**
- `save_preset(preset, workspace_root, scope) -> Path` — writes YAML to `<ws>/stacks/<name>.yaml` or `<vault>/patterns/effect-stacks/<name>.md` (markdown w/ frontmatter + body)
- `load_preset(name, workspace_root, vault_root) -> Preset` — workspace first, vault fallback; raises `FileNotFoundError` if neither finds it
- `list_presets(workspace_root, vault_root, scope: "workspace"|"vault"|"all") -> list[dict]` — enumerate
- `serialize_clip_to_preset(project, clip_ref, name, description, tags, created_by) -> Preset` — reuse Spec 2's `serialize_stack`, wrap in Preset model
- `validate_against_catalog(preset) -> list[str]` — returns list of warnings/errors; strict mode raises on any entry whose `mlt_service` is not in `effect_catalog.CATALOG` (checked via `find_by_service`)
- `apply_preset(project, target_clip_ref, preset, mode_override=None) -> dict` — honors `apply_hints.stack_order` (overridden by `mode_override` if given), delegates to Spec 2's `stack_ops.apply_paste`; returns `{"effects_applied": N, "blend_mode_hint": str|None, "required_producers": [...], "track_placement": str|None}`
- `promote_to_vault(name, workspace_root, vault_root, source_video_note_path: Path | None = None) -> Path` — copies workspace preset to vault, generates markdown body
- `render_vault_body(preset, source_video_note_path) -> str` — markdown template

**Vault markdown template:**
```markdown
---
{yaml frontmatter — full Preset model}
---

# {preset.name}

{preset.description}

**Tags:** {tags}
**Effects:** {len(effects)}
{if source_video_note_path exists: **Referenced from:** [[video-note-name]]}

## Effect stack

| # | Effect | MLT service |
|---|--------|-------------|
| 1 | {kdenlive_id or "—"} | {mlt_service} |
| ... | ... | ... |

## Notes
_(free-form — edit anytime)_
```

### `edit_mcp/server/tools.py` additions

Four new `@mcp.tool()` functions:

1. `effect_stack_preset(workspace_path, project_file, track, clip, name, description="", tags=None, apply_hints=None) -> dict` — serializes the clip's stack, validates against catalog (strict), writes to workspace. Returns `{"path": str, "effect_count": int}`.

2. `effect_stack_apply(workspace_path, project_file, track, clip, name, mode: str | None = None) -> dict` — loads preset (workspace → vault fallback), applies with `mode` (or preset's `apply_hints.stack_order` if `None`), snapshot, serialize. Returns `{"effects_applied": int, "mode": str, "snapshot_id": str, "blend_mode_hint": str|None, "track_placement_hint": str|None, "required_producers_hint": [...]}`.

3. `effect_stack_promote(workspace_path, name) -> dict` — copies workspace preset to vault. Looks up source video note via workspace manifest (`vault_note_path` field if set) for the "Referenced from" wikilink. Returns `{"workspace_path": str, "vault_path": str}`.

4. `effect_stack_list(workspace_path, scope: str = "all") -> dict` — lists presets. `scope ∈ {"workspace","vault","all"}`. Returns `{"presets": [{"name","scope","tags","effect_count","description"}]}`.

### Config

**Vault root resolution order:**
1. `forge-project.json` → `vault_root` field (new — absolute path)
2. `~/.claude/forge.json` → `personal_vault`
3. Fail gracefully if vault-scoped operation is called and neither is set (workspace-scoped operations still work)

## Data Flow

**Save preset:**
1. MCP `effect_stack_preset(track=2, clip=4, name="war-look", tags=["cinematic"])` →
2. Parse project → `serialize_clip_to_preset` → `validate_against_catalog` (strict) →
3. Write YAML to `<workspace>/stacks/war-look.yaml` →
4. Return `{path, effect_count}`.

**Apply preset:**
1. MCP `effect_stack_apply(track=3, clip=1, name="war-look")` →
2. Resolve preset: `<workspace>/stacks/war-look.yaml` → (miss) → `<vault>/patterns/effect-stacks/war-look.md` →
3. Snapshot, parse project, `apply_preset` (honors `stack_order`) →
4. Serialize → return applied count + hints.

**Promote:**
1. MCP `effect_stack_promote(name="war-look")` →
2. Read workspace preset → render markdown body with wikilink if source video note exists →
3. Write to `<vault>/patterns/effect-stacks/war-look.md` →
4. Return both paths.

## Decisions Locked

- **Storage:** two-tier — workspace-local (`<workspace>/stacks/<name>.yaml`) default; vault (`<vault>/patterns/effect-stacks/<name>.md`) via explicit `effect_stack_promote`.
- **Format:** YAML. Workspace = pure YAML. Vault = markdown with YAML frontmatter + auto-generated body.
- **Lookup order on apply:** workspace first, vault fallback.
- **Payload:** name, version (int), timestamps, created_by, tags, description, source (provenance), effects, apply_hints.
- **Versioning:** integer `version` field; bump on breaking schema changes.
- **Authorship:** tool-only. Vault markdown body is human-editable.
- **Apply conflict resolution:** `mode` param with default from preset's `apply_hints.stack_order` (= `append`). Overridable per call.
- **Validation on save:** strict — reject any effect whose `mlt_service` is not in catalog.
- **Apply-hints execution:** honor `blend_mode` + `stack_order`; surface `required_producers` and `track_placement` as response metadata (caller acts on them).
- **Promotion body:** auto-generated template with name, description, tags, effect list table, wikilink to source video note (if available), empty notes section.
- **Source video note linking:** wikilink if `workspace.manifest.vault_note_path` is set; otherwise omit.

## Error Handling

- **Save to workspace without `stacks/` dir** → create it.
- **Save with name that already exists** → overwrite (tool-only writes; no accidental hand edits to worry about).
- **Save with effect missing from catalog** → raise; error message lists the offending `mlt_service` and suggests `effect_list_common`.
- **Apply preset not found in either tier** → `FileNotFoundError` wrapped in `_err` listing searched paths.
- **Apply preset with effects now missing from catalog** (catalog regenerated after preset saved) → warn but proceed; include warnings in response.
- **Promote when vault root is not configured** → `_err("Vault root not configured — set vault_root in forge-project.json or personal_vault in forge.json").`
- **Promote workspace preset that doesn't exist** → `_err` listing available workspace presets.
- **Promote with existing vault file** → overwrite (same rationale as save).
- **List with malformed YAML file in the scope dir** → skip, include in response as `skipped: [{path, error}]`.
- **Apply with `mode="replace"` on a clip with pre-existing keyframes on filters being cleared** → keyframes lost (user's choice via replace).

## Open Questions

- None — scope clean; decisions locked in discussion + this doc.

## Approaches Considered

- **A — Two-tier YAML + strict validation (selected).** Matches user's mental model: "this-video" stacks in workspace, "recipes" in vault. Catches typos loud.
- **B — One-tier (workspace only, copy-to-vault via filesystem).** Simpler but loses auto-fallback and cross-project reuse.
- **C — Database-backed presets.** Searchable, indexed, but adds infrastructure and breaks the "preset travels with project" property.

## Next Steps

- [ ] Turn into a Forge spec
- [ ] Spec 5 (Masking) ships next
- [ ] Future: preset discovery UI in the vault
