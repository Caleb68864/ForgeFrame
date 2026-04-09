"""Workspace folder conventions and creation utilities."""
from __future__ import annotations

from pathlib import Path

WORKSPACE_FOLDERS: list[str] = [
    "media/raw",
    "media/proxies",
    "media/derived_audio",
    "media/processed",
    "transcripts",
    "markers",
    "projects/source",
    "projects/working_copies",
    "projects/snapshots",
    "renders/preview",
    "renders/final",
    "reports",
    "logs",
    "clips",
]


def create_workspace_structure(root: Path | str) -> None:
    """Create all standard workspace sub-directories under *root*."""
    root = Path(root)
    for folder in WORKSPACE_FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)


def validate_workspace_structure(root: Path | str) -> list[str]:
    """Return a list of expected folders that are missing from *root*."""
    root = Path(root)
    return [folder for folder in WORKSPACE_FOLDERS if not (root / folder).is_dir()]
