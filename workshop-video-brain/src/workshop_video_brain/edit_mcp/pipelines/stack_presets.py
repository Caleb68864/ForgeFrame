"""Effect stack preset data model and two-tier storage I/O.

Workspace tier: `<workspace_root>/stacks/<name>.yaml` (pure YAML).
Vault tier: `<vault_root>/patterns/effect-stacks/<name>.md` (YAML frontmatter
+ auto-generated markdown body).

Sub-Spec 1 scope: data model + save/load/list/resolve_vault_root. Catalog
validation, operations, and wikilink rendering live in Sub-Spec 2.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApplyHints",
    "PresetEffect",
    "Preset",
    "save_preset",
    "load_preset",
    "list_presets",
    "resolve_vault_root",
    "serialize_clip_to_preset",
    "validate_against_catalog",
    "apply_preset",
    "promote_to_vault",
    "render_vault_body",
]


_SLUG_RE = re.compile(r"[\\/]+")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


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


def _slugify(name: str) -> tuple[str, bool]:
    """Replace path separators with '-'. Returns (slug, was_modified)."""
    slug = _SLUG_RE.sub("-", name)
    return slug, slug != name


def _workspace_path(workspace_root: Path, name: str) -> Path:
    slug, _ = _slugify(name)
    return Path(workspace_root) / "stacks" / f"{slug}.yaml"


def _vault_path(vault_root: Path, name: str) -> Path:
    slug, _ = _slugify(name)
    return Path(vault_root) / "patterns" / "effect-stacks" / f"{slug}.md"


def _dump_yaml(preset: Preset) -> str:
    data = preset.model_dump(mode="json")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _default_vault_body(preset: Preset) -> str:
    tags_line = ", ".join(preset.tags) if preset.tags else "(none)"
    lines = [
        f"# {preset.name}",
        "",
        preset.description,
        "",
        f"**Tags:** {tags_line}",
        f"**Effects:** {len(preset.effects)}",
        "",
        "## Effect stack",
        "",
        "| # | Effect | MLT service |",
        "|---|--------|-------------|",
    ]
    for i, eff in enumerate(preset.effects, start=1):
        label = eff.kdenlive_id or "—"
        lines.append(f"| {i} | {label} | {eff.mlt_service} |")
    lines.extend([
        "",
        "## Notes",
        "_(free-form — edit anytime)_",
        "",
    ])
    return "\n".join(lines)


def save_preset(
    preset: Preset,
    *,
    workspace_root: Path | None = None,
    vault_root: Path | None = None,
    scope: Literal["workspace", "vault"] = "workspace",
    body_renderer: Callable[[Preset], str] | None = None,
) -> Path:
    """Write *preset* to the workspace or vault tier.

    Workspace writes pure YAML; vault writes markdown with YAML frontmatter
    and a generated body (or *body_renderer(preset)* when provided).
    """
    slug, _ = _slugify(preset.name)
    yaml_block = _dump_yaml(preset)

    if scope == "workspace":
        if workspace_root is None:
            raise ValueError("workspace_root is required for scope='workspace'")
        path = _workspace_path(workspace_root, preset.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_block, encoding="utf-8")
        return path

    if scope == "vault":
        if vault_root is None:
            raise ValueError("vault_root is required for scope='vault'")
        path = _vault_path(vault_root, preset.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = body_renderer(preset) if body_renderer is not None else _default_vault_body(preset)
        content = f"---\n{yaml_block}---\n\n{body}"
        path.write_text(content, encoding="utf-8")
        return path

    raise ValueError(f"Unknown scope: {scope!r}")


def _parse_markdown_frontmatter(text: str) -> dict:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Markdown file has no YAML frontmatter block")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("Frontmatter did not parse to a mapping")
    return data


def load_preset(
    name: str,
    workspace_root: Path | None,
    vault_root: Path | None = None,
) -> Preset:
    """Load a preset by *name*, preferring workspace over vault."""
    ws_path = _workspace_path(workspace_root, name) if workspace_root else None
    vault_path = _vault_path(vault_root, name) if vault_root else None

    if ws_path is not None and ws_path.is_file():
        data = yaml.safe_load(ws_path.read_text(encoding="utf-8"))
        return Preset.model_validate(data)

    if vault_path is not None and vault_path.is_file():
        data = _parse_markdown_frontmatter(vault_path.read_text(encoding="utf-8"))
        return Preset.model_validate(data)

    raise FileNotFoundError(
        f"Preset {name!r} not found. Searched: "
        f"{ws_path!s}, {vault_path!s}"
    )


def _summarize(preset: Preset, scope: str, path: Path) -> dict:
    return {
        "name": preset.name,
        "scope": scope,
        "tags": list(preset.tags),
        "effect_count": len(preset.effects),
        "description": preset.description,
        "path": str(path),
    }


def list_presets(
    workspace_root: Path | None,
    vault_root: Path | None = None,
    scope: Literal["workspace", "vault", "all"] = "all",
) -> dict:
    """Enumerate presets across tiers; malformed files go into ``skipped``."""
    presets: list[dict] = []
    skipped: list[dict] = []

    if scope in ("workspace", "all") and workspace_root is not None:
        ws_dir = Path(workspace_root) / "stacks"
        if ws_dir.is_dir():
            for f in sorted(ws_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(f.read_text(encoding="utf-8"))
                    preset = Preset.model_validate(data)
                    presets.append(_summarize(preset, "workspace", f))
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"path": str(f), "error": str(exc)})

    if scope in ("vault", "all") and vault_root is not None:
        vault_dir = Path(vault_root) / "patterns" / "effect-stacks"
        if vault_dir.is_dir():
            for f in sorted(vault_dir.glob("*.md")):
                try:
                    data = _parse_markdown_frontmatter(f.read_text(encoding="utf-8"))
                    preset = Preset.model_validate(data)
                    presets.append(_summarize(preset, "vault", f))
                except Exception as exc:  # noqa: BLE001
                    skipped.append({"path": str(f), "error": str(exc)})

    return {"presets": presets, "skipped": skipped}


def _safe_read_json(path: Path) -> dict | None:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def resolve_vault_root(
    project_json_path: Path = Path("forge-project.json"),
    forge_config_path: Path | None = None,
) -> Path | None:
    """Resolve the vault root from project config or the personal forge config."""
    if forge_config_path is None:
        forge_config_path = Path.home() / ".claude" / "forge.json"

    project_data = _safe_read_json(Path(project_json_path))
    if isinstance(project_data, dict):
        value = project_data.get("vault_root")
        if value:
            return Path(value).expanduser().resolve()

    forge_data = _safe_read_json(Path(forge_config_path))
    if isinstance(forge_data, dict):
        value = forge_data.get("personal_vault")
        if value:
            return Path(value).expanduser().resolve()

    return None


# ---------------------------------------------------------------------------
# Sub-Spec 2: operations pipeline
# ---------------------------------------------------------------------------

from workshop_video_brain.edit_mcp.pipelines import (  # noqa: E402
    effect_catalog,
    stack_ops,
)


def serialize_clip_to_preset(
    project,
    clip_ref: tuple[int, int],
    name: str,
    *,
    description: str = "",
    tags: tuple[str, ...] = (),
    created_by: str = "effect_stack_preset",
    apply_hints: ApplyHints | None = None,
) -> Preset:
    """Serialize a clip's filter stack into a fresh ``Preset``."""
    stack = stack_ops.serialize_stack(project, clip_ref)
    effects = tuple(
        PresetEffect(
            mlt_service=e["mlt_service"],
            kdenlive_id=e.get("kdenlive_id", ""),
            xml=e["xml"],
        )
        for e in stack["effects"]
    )
    now = datetime.now(tz=timezone.utc)
    return Preset(
        name=name,
        created_at=now,
        updated_at=now,
        created_by=created_by,
        tags=tuple(tags),
        description=description,
        source={"clip_ref": [clip_ref[0], clip_ref[1]]},
        effects=effects,
        apply_hints=apply_hints or ApplyHints(),
    )


def validate_against_catalog(preset: Preset, *, strict: bool = True) -> list[str]:
    """Verify each preset effect's mlt_service is in the catalog.

    With ``strict=True``, raises ``ValueError`` if any effect is unknown.
    With ``strict=False``, returns a list of warning messages (possibly empty).
    """
    warnings: list[str] = []
    for i, eff in enumerate(preset.effects):
        if effect_catalog.find_by_service(eff.mlt_service) is None:
            warnings.append(
                f"effects[{i}].mlt_service={eff.mlt_service!r} not found in "
                f"catalog (check effect_list_common for valid services)"
            )
    if strict and warnings:
        raise ValueError("; ".join(warnings))
    return warnings


def apply_preset(
    project,
    target_clip_ref: tuple[int, int],
    preset: Preset,
    *,
    mode_override: Literal["append", "prepend", "replace"] | None = None,
) -> dict:
    """Apply *preset* to *target_clip_ref*, returning a response dict."""
    mode = mode_override or preset.apply_hints.stack_order
    stack_dict = {"effects": [{"xml": e.xml} for e in preset.effects]}
    n = stack_ops.apply_paste(project, target_clip_ref, stack_dict, mode=mode)
    return {
        "effects_applied": n,
        "mode": mode,
        "blend_mode_hint": preset.apply_hints.blend_mode,
        "track_placement_hint": preset.apply_hints.track_placement,
        "required_producers_hint": tuple(preset.apply_hints.required_producers),
    }


def render_vault_body(
    preset: Preset,
    source_video_note_path: Path | None = None,
) -> str:
    """Render the vault markdown body for a preset.

    When *source_video_note_path* is given, embeds a ``[[stem]]`` wikilink
    line beneath the ``Effects:`` summary line.
    """
    tags_line = ", ".join(preset.tags) if preset.tags else "_none_"
    lines = [
        f"# {preset.name}",
        "",
        preset.description,
        "",
        f"**Tags:** {tags_line}",
        f"**Effects:** {len(preset.effects)}",
    ]
    if source_video_note_path is not None:
        stem = Path(source_video_note_path).stem
        lines.append(f"**Referenced from:** [[{stem}]]")
    lines.extend([
        "",
        "## Effect stack",
        "",
        "| # | mlt_service | kdenlive_id |",
        "|---|-------------|-------------|",
    ])
    for i, eff in enumerate(preset.effects):
        kid = eff.kdenlive_id or "—"
        lines.append(f"| {i} | {eff.mlt_service} | {kid} |")
    lines.extend([
        "",
        "## Notes",
        "_(free-form — edit anytime)_",
        "",
    ])
    return "\n".join(lines)


def promote_to_vault(
    name: str,
    workspace_root: Path,
    vault_root: Path,
    source_video_note_path: Path | None = None,
) -> Path:
    """Copy a workspace preset into the vault tier, rendering its markdown body."""
    preset = load_preset(name, workspace_root=workspace_root, vault_root=None)
    return save_preset(
        preset,
        vault_root=vault_root,
        scope="vault",
        body_renderer=lambda p: render_vault_body(
            p, source_video_note_path=source_video_note_path
        ),
    )
