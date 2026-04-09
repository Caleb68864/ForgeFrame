"""New project pipeline.

Creates a complete project workspace from a brain dump idea and kicks off the
video planning process: outline, script, and shot plan.
"""
from __future__ import annotations

import json
import os
import warnings
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.workspace.manager import WorkspaceManager


class NewProjectResult(BaseModel):
    """Result of creating a new video project."""

    project_title: str
    project_slug: str
    workspace_path: str
    vault_note_path: str
    media_folders_created: list[str]
    outline_generated: bool
    script_generated: bool
    shot_plan_generated: bool
    brain_dump: str


def _read_config() -> dict:
    """Read ~/.forgeframe/config.json if it exists."""
    config_path = Path.home() / ".forgeframe" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _resolve_projects_root(projects_root: Path | None) -> Path:
    """Resolve the projects root from argument, env, config, or cwd."""
    if projects_root is not None:
        return Path(projects_root)
    env_val = os.environ.get("WVB_WORKSPACE_ROOT")
    if env_val:
        return Path(env_val)
    cfg = _read_config()
    if cfg.get("projects_root"):
        return Path(cfg["projects_root"])
    return Path.cwd()


def _resolve_vault_path(vault_path: Path | None) -> Path | None:
    """Resolve the vault path from argument, env, or config. Returns None if not found."""
    if vault_path is not None:
        return Path(vault_path)
    env_val = os.environ.get("WVB_VAULT_PATH")
    if env_val:
        return Path(env_val)
    cfg = _read_config()
    if cfg.get("vault_path"):
        return Path(cfg["vault_path"])
    return None


def _create_media_subfolders(workspace_path: Path) -> list[str]:
    """Create organized media intake folders beyond the standard workspace structure.

    Creates:
        media/raw/video/
        media/raw/audio/
        media/raw/images/
        intake/
    """
    extra_folders = [
        "media/raw/video",
        "media/raw/audio",
        "media/raw/images",
        "intake",
    ]
    created: list[str] = []
    for folder in extra_folders:
        target = workspace_path / folder
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(folder)
        else:
            target.mkdir(parents=True, exist_ok=True)
    return created


def _create_vault_note(
    vault_path: Path,
    title: str,
    slug: str,
    workspace_path: Path,
    project_type: str,
    brain_dump: str,
) -> Path:
    """Create an Obsidian vault note for the new project.

    Returns the path to the created note.
    """
    from workshop_video_brain.production_brain.skills.video_note import create_or_update_note

    today = date.today().isoformat()

    data = {
        "title": title,
        "slug": slug,
        "status": "in-progress",
        "workspace_path": str(workspace_path),
        "content_type": project_type,
        "created": today,
        "vault_folder": "In Progress",
        "sections": {},
    }

    if brain_dump:
        data["sections"]["brain-dump"] = brain_dump

    note_path = create_or_update_note(
        workspace_root=workspace_path,
        vault_path=vault_path,
        data=data,
    )
    return note_path


def create_new_project(
    title: str,
    brain_dump: str = "",
    project_type: str = "tutorial",
    projects_root: Path | None = None,
    vault_path: Path | None = None,
) -> NewProjectResult:
    """Create a complete project workspace from a brain dump idea.

    Steps:
    1. Resolve paths (projects_root, vault_path)
    2. Create workspace directory with standard folder structure
    3. Create project-specific media intake folders
    4. Create Obsidian vault note (if vault_path available)
    5. Generate outline from brain_dump (if provided)
    6. Generate script from outline (if outline generated)
    7. Generate shot plan from script (if script generated)
    8. Return result with all paths and what was generated

    Args:
        title: Human-readable project title.
        brain_dump: Optional rough idea / description to kick off planning.
        project_type: Type of video: tutorial, review, vlog, build.
        projects_root: Root directory for all project workspaces.
            Resolved from config/env if not provided.
        vault_path: Root of the Obsidian vault.
            Resolved from config/env if not provided.

    Returns:
        NewProjectResult with all created paths and generation flags.
    """
    # ------------------------------------------------------------------
    # Step 1: Resolve paths
    # ------------------------------------------------------------------
    resolved_projects_root = _resolve_projects_root(projects_root)
    resolved_vault_path = _resolve_vault_path(vault_path)

    project_slug = slugify(title)
    workspace_path = resolved_projects_root / project_slug

    # ------------------------------------------------------------------
    # Step 2: Create workspace with standard folder structure
    # ------------------------------------------------------------------
    workspace = WorkspaceManager.create(
        title=title,
        media_root=str(workspace_path / "media" / "raw"),
        workspace_root=str(workspace_path),
    )

    # ------------------------------------------------------------------
    # Step 3: Create project-specific media intake folders
    # ------------------------------------------------------------------
    media_folders_created = _create_media_subfolders(workspace_path)

    # ------------------------------------------------------------------
    # Step 4: Create Obsidian vault note
    # ------------------------------------------------------------------
    vault_note_path = ""
    if resolved_vault_path is not None:
        try:
            note_path = _create_vault_note(
                vault_path=resolved_vault_path,
                title=title,
                slug=project_slug,
                workspace_path=workspace_path,
                project_type=project_type,
                brain_dump=brain_dump,
            )
            vault_note_path = str(note_path)
        except Exception as exc:
            warnings.warn(
                f"Failed to create vault note: {exc}",
                stacklevel=2,
            )
    else:
        warnings.warn(
            "No vault path configured. Obsidian note will not be created. "
            "Set WVB_VAULT_PATH or run `wvb init` to configure.",
            stacklevel=2,
        )

    # ------------------------------------------------------------------
    # Step 5: Generate outline from brain_dump
    # ------------------------------------------------------------------
    outline_generated = False
    outline_data: dict = {}
    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if brain_dump:
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        from workshop_video_brain.production_brain.notes.updater import update_section

        outline_md, outline_data = generate_outline(brain_dump, project_type)
        outline_generated = True

        # Save outline JSON to workspace reports
        (reports_dir / "outline.json").write_text(
            json.dumps(outline_data, indent=2), encoding="utf-8"
        )

        # Save outline markdown to vault note section
        if vault_note_path:
            try:
                update_section(vault_note_path, "outline", outline_md)
            except Exception as exc:
                warnings.warn(f"Failed to update outline section in note: {exc}", stacklevel=2)

    # ------------------------------------------------------------------
    # Step 6: Generate script from outline
    # ------------------------------------------------------------------
    script_generated = False
    script_data: dict = {}

    if outline_generated:
        from workshop_video_brain.production_brain.skills.script import generate_script
        from workshop_video_brain.production_brain.notes.updater import update_section

        script_md, script_data = generate_script(outline_data)
        script_generated = True

        # Save script JSON to workspace reports
        (reports_dir / "script.json").write_text(
            json.dumps(script_data, indent=2), encoding="utf-8"
        )

        # Save script markdown to vault note section
        if vault_note_path:
            try:
                update_section(vault_note_path, "script-draft", script_md)
            except Exception as exc:
                warnings.warn(f"Failed to update script section in note: {exc}", stacklevel=2)

    # ------------------------------------------------------------------
    # Step 7: Generate shot plan from script
    # ------------------------------------------------------------------
    shot_plan_generated = False

    if script_generated:
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        from workshop_video_brain.production_brain.notes.updater import update_section

        shot_plan_md, shot_plan_data = generate_shot_plan(script_data)
        shot_plan_generated = True

        # Save shot plan JSON to workspace reports
        (reports_dir / "shot_plan.json").write_text(
            json.dumps(shot_plan_data, indent=2), encoding="utf-8"
        )

        # Save shot plan markdown to vault note section
        if vault_note_path:
            try:
                update_section(vault_note_path, "shot-plan", shot_plan_md)
            except Exception as exc:
                warnings.warn(f"Failed to update shot-plan section in note: {exc}", stacklevel=2)

    # ------------------------------------------------------------------
    # Step 8: Return result
    # ------------------------------------------------------------------
    return NewProjectResult(
        project_title=title,
        project_slug=project_slug,
        workspace_path=str(workspace_path),
        vault_note_path=vault_note_path,
        media_folders_created=media_folders_created,
        outline_generated=outline_generated,
        script_generated=script_generated,
        shot_plan_generated=shot_plan_generated,
        brain_dump=brain_dump,
    )


def list_projects(projects_root: Path | None = None) -> list[dict]:
    """Scan projects_root for workspaces and return project summaries.

    Args:
        projects_root: Root directory to scan. Resolved from config/env if
            not provided.

    Returns:
        List of dicts with: name, slug, status, workspace_path, vault_note_path.
        Empty list if no projects found or projects_root does not exist.
    """
    resolved_root = _resolve_projects_root(projects_root)
    if not resolved_root.is_dir():
        return []

    projects: list[dict] = []
    for candidate in sorted(resolved_root.iterdir()):
        if not candidate.is_dir():
            continue
        manifest_path = candidate / "workspace.yaml"
        if not manifest_path.exists():
            continue
        try:
            from workshop_video_brain.workspace.manifest import read_manifest
            manifest = read_manifest(candidate)
            projects.append({
                "name": manifest.project_title,
                "slug": manifest.slug,
                "status": manifest.status if isinstance(manifest.status, str) else manifest.status.value,
                "workspace_path": str(candidate),
                "vault_note_path": manifest.vault_note_path or "",
            })
        except Exception:
            # Skip workspaces with unreadable manifests
            continue

    return projects
