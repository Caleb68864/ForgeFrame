"""Path utilities: safe filenames, versioned paths, workspace-relative helpers."""
from __future__ import annotations

import re
from pathlib import Path


def safe_filename(name: str) -> str:
    """Strip illegal filename characters and truncate to 200 chars.

    Removes ``<>:"/\\|?*``, replaces spaces with hyphens.
    """
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = cleaned.replace(" ", "-")
    return cleaned[:200]


def versioned_path(base: Path | str, extension: str) -> Path:
    """Return *base.extension* if it does not exist, otherwise *base-1.extension*, etc."""
    base = Path(base)
    candidate = base.with_suffix(extension)
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = base.with_name(f"{base.name}-{counter}").with_suffix(extension)
        if not candidate.exists():
            return candidate
        counter += 1


def workspace_relative(absolute: Path | str, workspace_root: Path | str) -> str:
    """Return *absolute* as a string relative to *workspace_root*."""
    return str(Path(absolute).relative_to(Path(workspace_root)))


def ensure_dir(path: Path | str) -> Path:
    """Create *path* and all parents; return the Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
