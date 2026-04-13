"""Workspace manager: create, open, and update workspaces."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from workshop_video_brain.core.models.enums import ProjectStatus
from workshop_video_brain.core.models.project import VideoProject
from workshop_video_brain.core.models.workspace import KeyframeDefaults, Workspace
from workshop_video_brain.core.utils.naming import slugify

from .folders import create_workspace_structure
from .manifest import WorkspaceManifest, read_manifest, write_manifest


class WorkspaceManager:
    """Manage workspace lifecycle: creation, opening, status updates."""

    @staticmethod
    def create(
        title: str,
        media_root: str | Path,
        config: dict | None = None,
        workspace_root: str | Path | None = None,
    ) -> Workspace:
        """Create a new workspace directory structure and manifest.

        Args:
            title: Human-readable project title.
            media_root: Absolute path to the media source directory.
            config: Optional extra configuration dict stored in the workspace.
            workspace_root: Where to create the workspace.  Defaults to
                            ``media_root / slug``.
        """
        slug = slugify(title)
        media_root = Path(media_root)

        if workspace_root is None:
            workspace_root = media_root.parent / slug
        workspace_root = Path(workspace_root)

        create_workspace_structure(workspace_root)

        project = VideoProject(
            title=title,
            slug=slug,
            status=ProjectStatus.idea,
        )

        keyframe_defaults = KeyframeDefaults()
        manifest = WorkspaceManifest(
            workspace_id=project.id,
            project_title=title,
            slug=slug,
            status=ProjectStatus.idea,
            media_root=str(media_root),
            keyframe_defaults=keyframe_defaults,
        )
        write_manifest(workspace_root, manifest)

        workspace = Workspace(
            id=project.id,
            project=project,
            media_root=str(media_root),
            workspace_root=str(workspace_root),
            config=config or {},
            keyframe_defaults=keyframe_defaults,
        )
        return workspace

    @staticmethod
    def open(path: str | Path) -> Workspace:
        """Load an existing workspace from *path*."""
        path = Path(path)
        manifest = read_manifest(path)

        project = VideoProject(
            id=manifest.workspace_id,
            title=manifest.project_title,
            slug=manifest.slug,
            status=manifest.status,
            content_type=manifest.content_type,
        )
        return Workspace(
            id=manifest.workspace_id,
            project=project,
            media_root=manifest.media_root,
            vault_note_path=manifest.vault_note_path,
            workspace_root=str(path),
            keyframe_defaults=manifest.keyframe_defaults,
        )

    @staticmethod
    def save_manifest(workspace: Workspace) -> None:
        """Persist the workspace manifest to disk."""
        manifest = WorkspaceManifest(
            workspace_id=workspace.id,
            project_title=workspace.project.title,
            slug=workspace.project.slug,
            status=workspace.project.status,
            content_type=workspace.project.content_type,
            vault_note_path=workspace.vault_note_path,
            media_root=workspace.media_root,
            keyframe_defaults=workspace.keyframe_defaults,
        )
        write_manifest(Path(workspace.workspace_root), manifest)

    @staticmethod
    def update_status(workspace: Workspace, new_status: ProjectStatus | str) -> None:
        """Update the project status in memory and flush the manifest."""
        # Workspace and VideoProject use use_enum_values=True so we can assign
        # either the enum member or its string value directly.
        workspace.project.status = new_status  # type: ignore[assignment]
        workspace.project.updated_at = datetime.now(tz=timezone.utc)
        WorkspaceManager.save_manifest(workspace)
