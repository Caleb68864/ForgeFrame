"""B-Roll Whisperer skill helper.

Reads transcript files from a workspace, detects B-roll opportunities, and
saves the formatted results to an Obsidian note.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
    detect_broll_opportunities,
    format_broll_suggestions,
)


def extract_and_format(workspace_root: Path) -> tuple[str, list[dict]]:
    """Read transcripts from workspace, detect B-roll opportunities, and format.

    Reads all ``*_transcript.json`` files from ``{workspace_root}/transcripts/``,
    runs :func:`detect_broll_opportunities` over each, then formats the
    combined results as Markdown.

    Args:
        workspace_root: Path to the workspace root directory.

    Returns:
        A ``(markdown, suggestions)`` tuple where *markdown* is the formatted
        Markdown string and *suggestions* is the raw list of suggestion dicts.
    """
    transcripts_dir = workspace_root / "transcripts"
    all_suggestions: list[dict] = []

    if transcripts_dir.exists():
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                transcript = Transcript.from_json(
                    json_path.read_text(encoding="utf-8")
                )
                suggestions = detect_broll_opportunities(transcript)
                all_suggestions.extend(suggestions)
            except Exception:
                pass

    markdown = format_broll_suggestions(all_suggestions)
    return markdown, all_suggestions


def save_to_note(
    workspace_root: Path,
    vault_path: Path,
    markdown: str,
) -> Path:
    """Save B-roll suggestions to the Obsidian video note.

    Writes *markdown* into the ``broll-suggestions`` section of the workspace's
    video note. Creates the note file if it does not yet exist.

    Args:
        workspace_root: Path to the workspace root directory.
        vault_path: Path to the Obsidian vault root.
        markdown: Formatted Markdown to save.

    Returns:
        Path to the updated (or created) note file.
    """
    from workshop_video_brain.production_brain.notes.updater import update_section

    note_path = _resolve_note_path(workspace_root, vault_path)

    if not note_path.exists():
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            _default_note_content(workspace_root),
            encoding="utf-8",
        )

    update_section(note_path, "broll-suggestions", markdown)
    return note_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_note_path(workspace_root: Path, vault_path: Path) -> Path:
    """Determine the Obsidian note path for this workspace."""
    try:
        from workshop_video_brain.workspace.manifest import read_manifest
        manifest = read_manifest(workspace_root)
        slug = manifest.slug or manifest.project_title.lower().replace(" ", "-")
    except Exception:
        slug = workspace_root.name
    return vault_path / "videos" / f"{slug}.md"


def _default_note_content(workspace_root: Path) -> str:
    """Generate minimal note content when no note exists yet."""
    title = workspace_root.name
    return (
        f"---\ntitle: {title}\nstatus: editing\n---\n\n"
        f"# {title}\n\n"
        f"Workspace: `{workspace_root}`\n"
    )
