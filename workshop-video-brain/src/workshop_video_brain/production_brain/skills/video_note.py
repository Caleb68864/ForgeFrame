"""Video note skill engine.

Creates or updates an Obsidian video project note.
Uses NoteWriter for new notes and NoteUpdater for existing ones.
Syncs frontmatter from workspace manifest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workshop_video_brain.production_brain.notes.writer import NoteWriter
from workshop_video_brain.production_brain.notes.updater import (
    update_frontmatter,
    update_section,
)
from workshop_video_brain.production_brain.notes.frontmatter import parse_note


def create_or_update_note(
    workspace_root: Path,
    vault_path: Path,
    data: dict,
) -> Path:
    """Create a new Obsidian video note or update an existing one.

    If the note does not exist at the resolved path, a new note is created
    from the default template. If it does exist, frontmatter is synced and
    any sections provided in data['sections'] are updated.

    Manual edits outside section boundaries are always preserved.

    Args:
        workspace_root: Root of the workspace directory.
        vault_path: Root of the Obsidian vault.
        data: Dict with optional keys:
            title (str), slug (str), status (str), content_type (str),
            vault_folder (str), sections (dict[section_name, markdown_content]),
            plus any extra frontmatter fields to sync.

    Returns:
        Path to the created or updated note.
    """
    # Resolve note path
    note_path = _resolve_note_path(vault_path, data)

    if note_path.exists():
        _update_existing_note(note_path, workspace_root, data)
    else:
        _create_new_note(note_path, vault_path, workspace_root, data)

    return note_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_note_path(vault_path: Path, data: dict) -> Path:
    """Determine the note path from data dict."""
    vault_folder = data.get("vault_folder", "Videos/In-Progress")
    slug = data.get("slug") or _slugify(data.get("title", "untitled"))
    filename = f"{slug}.md"
    return vault_path / vault_folder / filename


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _build_frontmatter(workspace_root: Path, data: dict) -> dict[str, Any]:
    """Build frontmatter dict from data and workspace manifest."""
    # Try to read manifest for authoritative fields
    manifest_data: dict = {}
    manifest_path = workspace_root / "workspace.yaml"
    if manifest_path.exists():
        try:
            import yaml
            manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    fm: dict[str, Any] = {
        "title": (
            data.get("title")
            or manifest_data.get("project_title")
            or "Untitled"
        ),
        "slug": (
            data.get("slug")
            or manifest_data.get("slug")
            or _slugify(data.get("title", "untitled"))
        ),
        "status": (
            data.get("status")
            or manifest_data.get("status")
            or "idea"
        ),
        "created": today,
        "updated": today,
        "content_type": (
            data.get("content_type")
            or manifest_data.get("content_type")
            or "tutorial"
        ),
        "tags": data.get("tags", []),
    }

    # Allow caller to pass arbitrary extra frontmatter fields
    for key, val in data.items():
        if key not in ("sections", "vault_folder") and key not in fm:
            fm[key] = val

    return fm


def _build_note_body(data: dict) -> str:
    """Build the initial note body with empty section placeholders."""
    title = data.get("title", "Untitled")
    sections_data = data.get("sections", {})

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")

    section_names = ["outline", "script", "shot-plan", "transcript", "edit-notes",
                     "publish-checklist", "manual-notes"]

    for section_name in section_names:
        open_tag = f"<!-- wvb:section:{section_name} -->"
        close_tag = f"<!-- /wvb:section:{section_name} -->"
        content = sections_data.get(section_name, "")
        if content:
            lines.append(open_tag)
            lines.append(content)
            lines.append(close_tag)
        else:
            lines.append(open_tag)
            lines.append(close_tag)
        lines.append("")

    return "\n".join(lines)


def _create_new_note(
    note_path: Path,
    vault_path: Path,
    workspace_root: Path,
    data: dict,
) -> None:
    """Create a new note using the template system."""
    from workshop_video_brain.production_brain.notes.frontmatter import write_note

    fm = _build_frontmatter(workspace_root, data)
    body = _build_note_body(data)

    note_path.parent.mkdir(parents=True, exist_ok=True)
    write_note(note_path, fm, body)


def _update_existing_note(
    note_path: Path,
    workspace_root: Path,
    data: dict,
) -> None:
    """Update frontmatter and sections of an existing note."""
    # Build frontmatter updates (only fields present in data / manifest)
    fm_updates = _build_frontmatter(workspace_root, data)
    # Always update the 'updated' timestamp
    fm_updates["updated"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Read existing frontmatter to avoid clobbering extra keys
    existing_fm, _ = parse_note(note_path)
    # Preserve keys in existing fm that are not in our update set
    merged = {**existing_fm, **fm_updates}

    # Write merged frontmatter
    update_frontmatter(note_path, merged)

    # Update each section that has new content
    sections = data.get("sections", {})
    for section_name, content in sections.items():
        if content:
            update_section(note_path, section_name, content)
