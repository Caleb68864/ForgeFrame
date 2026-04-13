---
type: phase-spec
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-presets.md"
sub_spec_number: 1
title: "Preset Data Model + Storage I/O"
date: 2026-04-13
dependencies: []
---

# Sub-Spec 1: Preset Data Model + Storage I/O

Refined from `docs/specs/2026-04-13-stack-presets.md` — Stack Presets feature.

## Scope

Create the new pipeline module `workshop_video_brain/edit_mcp/pipelines/stack_presets.py` containing the Pydantic v2 preset model family (`Preset`, `PresetEffect`, `ApplyHints`) and the storage I/O surface (`save_preset`, `load_preset`, `list_presets`, `resolve_vault_root`).

Two storage tiers:
- **Workspace (YAML):** `<workspace_root>/stacks/<name>.yaml` — pure YAML serialization of the `Preset` model.
- **Vault (Markdown w/ frontmatter):** `<vault_root>/patterns/effect-stacks/<name>.md` — YAML frontmatter block followed by an auto-generated human-readable body (rendered by Sub-Spec 2; this sub-spec only needs to load existing markdown frontmatter and write YAML-only files).

Catalog validation is NOT performed here — Sub-Spec 2 owns that. This sub-spec only handles I/O round-trip.

`resolve_vault_root` looks up vault location from (in order): `forge-project.json.vault_root`, then `~/.claude/forge.json.personal_vault`. Returns `None` if neither resolves. This sub-spec extends the optional `vault_root` field in `forge-project.json` (read-only consumption — the schema is loose JSON, no Pydantic model to update).

## Interface Contracts

### Provides
- `Preset` (pydantic.BaseModel) — full preset record.
- `PresetEffect` (pydantic.BaseModel) — single-filter entry holding verbatim XML.
- `ApplyHints` (pydantic.BaseModel) — apply-time hint bundle.
- `save_preset(preset: Preset, *, workspace_root: Path | None = None, vault_root: Path | None = None, scope: Literal["workspace","vault"] = "workspace", body_renderer: Callable[[Preset], str] | None = None) -> Path`
- `load_preset(name: str, workspace_root: Path | None, vault_root: Path | None) -> Preset`
- `list_presets(workspace_root: Path | None, vault_root: Path | None, scope: Literal["workspace","vault","all"] = "all") -> dict` returning `{"presets": [...], "skipped": [...]}`.
- `resolve_vault_root(project_json_path: Path, forge_config_path: Path | None = None) -> Path | None`

### Requires
- PyYAML (already in `pyproject.toml` as `pyyaml>=6.0`).
- Pydantic v2 (already a tech-stack dependency).
- No dependency on Sub-Spec 2 or the catalog — pure data + I/O.

### Shared State
- Filesystem under `<workspace_root>/stacks/` (created on demand).
- Filesystem under `<vault_root>/patterns/effect-stacks/` (created on demand when scope=vault).
- Read-only consumers of `forge-project.json` and `~/.claude/forge.json`.

## Implementation Steps

### Step 1: Write failing tests
- **File:** `tests/unit/test_stack_presets_io.py` (new)
- **Tests:**
  - `test_module_exports` — `from workshop_video_brain.edit_mcp.pipelines import stack_presets` and assert `Preset`, `PresetEffect`, `ApplyHints`, `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root` all bound.
  - `test_preset_model_field_defaults` — Construct `Preset(name="x", effects=())` and assert `version == 1`, `tags == ()`, `description == ""`, `source is None`, `apply_hints` is a default `ApplyHints` with `stack_order == "append"`.
  - `test_apply_hints_literal_validation` — `ApplyHints(stack_order="bogus")` raises `pydantic.ValidationError`.
  - `test_extra_fields_ignored` — Build a YAML doc with an unknown top-level key (e.g. `foo: bar`); load via `Preset.model_validate(yaml.safe_load(...))`; assert no error (config `extra="ignore"`).
  - `test_save_then_load_workspace_round_trip` — Build a `Preset` with one `PresetEffect(xml="<filter ...>...</filter>")`. `save_preset(p, workspace_root=tmp, scope="workspace")`. Read raw file, then `load_preset(p.name, workspace_root=tmp, vault_root=None)`. Assert reloaded preset equals original (use `model_dump(mode='json')` for comparison). XML string is byte-identical.
  - `test_save_creates_stacks_dir` — On a workspace_root with no `stacks/` subdir, `save_preset` creates it.
  - `test_save_workspace_path_is_correct` — Returned path equals `workspace_root / "stacks" / f"{preset.name}.yaml"`.
  - `test_save_vault_writes_markdown_with_frontmatter` — `save_preset(p, vault_root=tmp, scope="vault", body_renderer=lambda preset: "BODY-MARKER")`. Assert file at `tmp/patterns/effect-stacks/<name>.md` exists. Read text. Assert it starts with `---\n`, contains `name: <name>`, has a closing `---\n`, then `BODY-MARKER`.
  - `test_load_prefers_workspace_over_vault` — Save same name to both tiers with different descriptions. `load_preset(name, workspace_root, vault_root)` returns workspace version.
  - `test_load_falls_back_to_vault` — Save to vault only. `load_preset(name, workspace_root=tmp_empty, vault_root=tmp_with_vault)` returns vault version.
  - `test_load_missing_raises_with_both_paths` — `load_preset("nope", ws, vault)` raises `FileNotFoundError` whose message contains both the expected workspace path and the vault path strings.
  - `test_load_vault_markdown_parses_frontmatter` — Write a markdown file with valid frontmatter manually, then `load_preset` returns a valid `Preset`.
  - `test_list_enumerates_both_tiers` — Save 2 presets to workspace, 3 to vault. `list_presets(ws, vault, scope="all")` returns `presets` of length 5; each entry has `{name, scope, tags, effect_count, description, path}`.
  - `test_list_workspace_scope_only` — Same setup; `scope="workspace"` returns only the 2 workspace entries; vault entries excluded.
  - `test_list_skips_malformed_files` — Place a corrupt YAML file in workspace `stacks/`. `list_presets` succeeds; the corrupt file appears in the `skipped` list with `{path, error}`.
  - `test_list_empty_returns_empty_lists` — `list_presets(empty_ws, empty_vault, scope="all")` returns `{"presets": [], "skipped": []}`.
  - `test_list_workspace_and_vault_share_name` — Same name in both; `scope="all"` returns both with their respective scope labels.
  - `test_resolve_vault_root_from_project_json` — Write `forge-project.json` with `vault_root: "/tmp/v"`. `resolve_vault_root(project_json_path, forge_config_path=missing)` returns `Path("/tmp/v").expanduser().resolve()`.
  - `test_resolve_vault_root_from_personal_vault` — `forge-project.json` has no `vault_root`. Write a fake forge-config JSON with `personal_vault: "/tmp/p"`. Returns `Path("/tmp/p").expanduser().resolve()`.
  - `test_resolve_vault_root_returns_none_when_neither_set` — Both files empty/missing → returns `None`.
  - `test_resolve_vault_root_expands_user_and_relative` — `vault_root: "~/foo"` resolves to absolute home-expanded path.
  - `test_save_slugifies_path_separators` — `save_preset(Preset(name="my/preset", ...), ws, scope="workspace")` writes `my-preset.yaml` (separators replaced with `-`); returns the slugified path.
- **Run:** `uv run pytest tests/unit/test_stack_presets_io.py -v`
- **Expected:** FAIL (module does not exist).

### Step 2: Create the module skeleton
- **File:** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` (new)
- **Pattern:** Follow `workshop_video_brain/workspace/manifest.py` for Pydantic + YAML idioms (use `pydantic.BaseModel` with `model_config`, use `yaml.safe_dump` / `yaml.safe_load`).
- **Action:** Implement:
  ```python
  from __future__ import annotations
  from datetime import datetime, timezone
  from pathlib import Path
  from typing import Callable, Literal
  import json
  import re
  import yaml
  from pydantic import BaseModel, ConfigDict, Field

  _SLUG_RE = re.compile(r"[\\/]+")

  class ApplyHints(BaseModel):
      model_config = ConfigDict(extra="ignore", validate_assignment=True)
      blend_mode: str | None = None
      stack_order: Literal["append", "prepend", "replace"] = "append"
      track_placement: str | None = None
      required_producers: tuple[str, ...] = ()

  class PresetEffect(BaseModel):
      model_config = ConfigDict(extra="ignore", validate_assignment=True)
      mlt_service: str
      kdenlive_id: str = ""
      xml: str

  class Preset(BaseModel):
      model_config = ConfigDict(extra="ignore", validate_assignment=True)
      name: str
      version: int = 1
      created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
      updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
      created_by: str = ""
      tags: tuple[str, ...] = ()
      description: str = ""
      source: dict | None = None
      effects: tuple[PresetEffect, ...]
      apply_hints: ApplyHints = Field(default_factory=ApplyHints)
  ```
- Also implement `_slugify(name)`, `_workspace_path(ws, name)`, `_vault_path(vault, name)`, helpers.

### Step 3: Implement `save_preset`
- **Action:** Slugify `preset.name`'s path separators, ensure parent dir exists, write YAML for workspace OR markdown w/ frontmatter for vault. For vault, the body comes from `body_renderer(preset)` if provided, else an empty string. Return resolved `Path`.
- **YAML encoding:** Use `yaml.safe_dump(preset.model_dump(mode="json"), sort_keys=False, allow_unicode=True)`. Datetime fields will serialize as ISO strings via `mode="json"` — this guarantees round-trip stability.
- **Markdown frontmatter:** `f"---\n{yaml_block}---\n\n{body}"`.

### Step 4: Implement `load_preset`
- **Action:** Build candidate paths `[workspace_root/stacks/{name}.yaml]` (if `workspace_root`), `[vault_root/patterns/effect-stacks/{name}.md]` (if `vault_root`). For each existing path: parse YAML (or split frontmatter for `.md` — match `^---\n(.*?)\n---` with `re.DOTALL`); validate via `Preset.model_validate(data)`. Return first hit.
- If neither found: raise `FileNotFoundError(f"Preset '{name}' not found. Searched: {ws_path!s}, {vault_path!s}")`.

### Step 5: Implement `list_presets`
- **Action:** For each in-scope tier, glob `*.yaml` (workspace) or `*.md` (vault). Try to load each; on success, append `{"name": p.name, "scope": "workspace"|"vault", "tags": list(p.tags), "effect_count": len(p.effects), "description": p.description, "path": str(file)}`. On failure, append to `skipped` with `{"path": str(file), "error": str(exc)}`. Return `{"presets": [...], "skipped": [...]}`.

### Step 6: Implement `resolve_vault_root`
- **Action:** Read `project_json_path` if exists, get `.get("vault_root")`. If truthy, return `Path(value).expanduser().resolve()`. Else read `forge_config_path` (default `Path.home() / ".claude" / "forge.json"`) if it exists, get `.get("personal_vault")`. If truthy, resolve and return. Else return `None`. All file-read failures return `None` silently (this is a best-effort lookup).

### Step 7: Verify tests pass
- **Run:** `uv run pytest tests/unit/test_stack_presets_io.py -v`
- **Expected:** PASS.

### Step 8: Run full suite for regressions
- **Run:** `uv run pytest tests/ -v`
- **Expected:** PASS — baseline tests unchanged.

### Step 9: Commit
- **Stage:** `git add workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py tests/unit/test_stack_presets_io.py`
- **Message:** `feat: preset data model + storage io for effect stack presets`

## Acceptance Criteria

- `[STRUCTURAL]` Module exports `Preset`, `PresetEffect`, `ApplyHints` (Pydantic BaseModels), `save_preset`, `load_preset`, `list_presets`, `resolve_vault_root`.
- `[STRUCTURAL]` `Preset` fields: `name: str`, `version: int = 1`, `created_at: datetime`, `updated_at: datetime`, `created_by: str`, `tags: tuple[str, ...] = ()`, `description: str = ""`, `source: dict | None = None`, `effects: tuple[PresetEffect, ...]`, `apply_hints: ApplyHints = ApplyHints()`.
- `[STRUCTURAL]` `PresetEffect` fields: `mlt_service: str`, `kdenlive_id: str = ""`, `xml: str`.
- `[STRUCTURAL]` `ApplyHints` fields: `blend_mode: str | None = None`, `stack_order: Literal["append","prepend","replace"] = "append"`, `track_placement: str | None = None`, `required_producers: tuple[str, ...] = ()`.
- `[BEHAVIORAL]` `save_preset(preset, workspace_root, scope="workspace")` writes YAML to `<workspace_root>/stacks/<preset.name>.yaml`; creates `stacks/` dir if absent.
- `[BEHAVIORAL]` `save_preset(preset, vault_root=..., scope="vault")` writes markdown with YAML frontmatter + body to `<vault_root>/patterns/effect-stacks/<preset.name>.md`.
- `[BEHAVIORAL]` `load_preset(name, workspace_root, vault_root)` prefers workspace; falls back to vault. Returns validated `Preset`.
- `[BEHAVIORAL]` `load_preset` with missing name raises `FileNotFoundError` listing both searched paths.
- `[BEHAVIORAL]` `list_presets(...)` enumerates both tiers; returns `{presets: [...], skipped: [...]}`.
- `[BEHAVIORAL]` `resolve_vault_root(...)` returns first of `forge-project.json.vault_root`, `~/.claude/forge.json.personal_vault`, or `None`.
- `[BEHAVIORAL]` YAML round-trip preserves data; XML strings byte-identical.
- `[BEHAVIORAL]` Vault markdown frontmatter is valid YAML.
- `[MECHANICAL]` `uv run pytest tests/unit/test_stack_presets_io.py -v` passes.

## Completeness Checklist

### `Preset`
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| name | str | required | save path slug, list display |
| version | int (default 1) | optional | future migration |
| created_at | datetime | optional (auto) | metadata |
| updated_at | datetime | optional (auto) | metadata |
| created_by | str (default "") | optional | provenance |
| tags | tuple[str, ...] (default ()) | optional | list filter, vault body |
| description | str (default "") | optional | list display, vault body |
| source | dict \| None (default None) | optional | provenance hint |
| effects | tuple[PresetEffect, ...] | required | apply pipeline |
| apply_hints | ApplyHints (default factory) | optional | apply pipeline |

### `PresetEffect`
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| mlt_service | str | required | catalog validation (Sub-Spec 2) |
| kdenlive_id | str (default "") | optional | display |
| xml | str | required | apply_paste rewriter |

### `ApplyHints`
| Field | Type | Required | Used By |
|-------|------|----------|---------|
| blend_mode | str \| None | optional | response hint |
| stack_order | Literal["append","prepend","replace"] (default "append") | optional | apply mode default |
| track_placement | str \| None | optional | response hint |
| required_producers | tuple[str, ...] (default ()) | optional | response hint |

### Resource paths
- Workspace preset path: `<workspace_root>/stacks/<slug(name)>.yaml`
- Vault preset path: `<vault_root>/patterns/effect-stacks/<slug(name)>.md`
- Forge config path: `~/.claude/forge.json` (read key `personal_vault`)
- Project config path: `<repo>/forge-project.json` (read optional key `vault_root`)

## Verification Commands

- **Build:** `uv sync`
- **Tests:** `uv run pytest tests/unit/test_stack_presets_io.py -v`
- **Full suite:** `uv run pytest tests/ -v`
- **Acceptance:** Imports + round-trip + fallback + None-resolution all proven by the unit-test suite above.

## Patterns to Follow

- `workshop-video-brain/src/workshop_video_brain/workspace/manifest.py` — pydantic + YAML idiom (`yaml.safe_dump` / `yaml.safe_load`, `model_config`, ISO-datetime via JSON-mode dump).
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_ops.py` — module-level `__all__`, `from __future__ import annotations`, module docstring.
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` — pydantic-free dataclass-style module-level data; mirror the docstring + `__all__` shape.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/stack_presets.py` | Create | Preset model + I/O |
| `tests/unit/test_stack_presets_io.py` | Create | Round-trip + fallback + resolution tests |
