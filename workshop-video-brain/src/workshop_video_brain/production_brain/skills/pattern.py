"""Pattern Brain skill engine.

Reads a transcript from a workspace, extracts MYOG build data, and
provides helpers to save build notes and update an Obsidian note.
"""
from __future__ import annotations

import json
from pathlib import Path


def extract_and_format(workspace_root: Path) -> dict:
    """Read the first available transcript from workspace, extract and format build data.

    Args:
        workspace_root: Path to the workspace root directory.

    Returns:
        Dict with keys:
            build_data (BuildData), overlay_text (list[dict]),
            build_notes_md (str).

    Raises:
        FileNotFoundError: If no transcript JSON is found in the workspace.
    """
    from workshop_video_brain.core.models.transcript import Transcript
    from workshop_video_brain.edit_mcp.pipelines.pattern_brain import (
        extract_build_data,
        generate_overlay_text,
        generate_build_notes,
    )

    transcripts_dir = workspace_root / "transcripts"
    json_files = sorted(transcripts_dir.glob("*_transcript.json")) if transcripts_dir.exists() else []
    if not json_files:
        raise FileNotFoundError(
            f"No transcript JSON files found under {transcripts_dir}"
        )

    # Use the first transcript found
    transcript_path = json_files[0]
    transcript = Transcript.from_json(transcript_path.read_text(encoding="utf-8"))

    # Try to read project title from workspace manifest
    project_title = ""
    manifest_path = workspace_root / "workspace.yaml"
    if manifest_path.exists():
        try:
            import yaml
            manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            project_title = manifest_data.get("project_title", "")
        except Exception:
            pass

    build_data = extract_build_data(transcript, project_title=project_title)
    overlay_text = generate_overlay_text(build_data)
    build_notes_md = generate_build_notes(build_data)

    return {
        "build_data": build_data,
        "overlay_text": overlay_text,
        "build_notes_md": build_notes_md,
    }


def save_build_notes(workspace_root: Path, notes_md: str) -> Path:
    """Save build notes markdown to reports/build_notes.md.

    Args:
        workspace_root: Path to the workspace root directory.
        notes_md: Markdown string to write.

    Returns:
        Path to the written file.
    """
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "build_notes.md"
    out_path.write_text(notes_md, encoding="utf-8")
    return out_path


def save_to_note(workspace_root: Path, vault_path: Path, content: str) -> Path:
    """Save build data content into an Obsidian note under the build-data section.

    Looks for an existing note by the workspace slug. If not found, creates one.
    Injects content into the ``<!-- wvb:section:build-data -->`` section.

    Args:
        workspace_root: Path to the workspace root directory.
        vault_path: Root of the Obsidian vault.
        content: Markdown content to write into the build-data section.

    Returns:
        Path to the created or updated note.
    """
    from workshop_video_brain.production_brain.skills.video_note import create_or_update_note

    note_path = create_or_update_note(
        workspace_root=workspace_root,
        vault_path=vault_path,
        data={
            "sections": {
                "build-data": content,
            },
        },
    )
    return note_path
