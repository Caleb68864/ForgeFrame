"""Workspace package: folder conventions, manifest, snapshot, manager."""
from .folders import WORKSPACE_FOLDERS, create_workspace_structure, validate_workspace_structure
from .manifest import WorkspaceManifest, read_manifest, write_manifest
from .manager import WorkspaceManager
from .snapshot import create as create_snapshot
from .snapshot import list_snapshots, restore as restore_snapshot

__all__ = [
    "WORKSPACE_FOLDERS",
    "create_workspace_structure",
    "validate_workspace_structure",
    "WorkspaceManifest",
    "read_manifest",
    "write_manifest",
    "WorkspaceManager",
    "create_snapshot",
    "restore_snapshot",
    "list_snapshots",
]
