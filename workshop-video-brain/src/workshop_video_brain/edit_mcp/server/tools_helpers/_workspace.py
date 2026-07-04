"""Workspace validation + workspace-relative media/root finders.

Path-level primitives shared by nearly every tool: validate a
``workspace_path``, open its :class:`WorkspaceManager`, walk up for a
``workspace.yaml`` marker, and resolve a source file (explicit or newest in
``media/raw``).
"""
from __future__ import annotations

from pathlib import Path


def _validate_workspace_path(workspace_path: str) -> Path:
    """Validate workspace_path: must be non-empty, exist, and be a directory.

    Raises ValueError with a clear message if any check fails.
    """
    if not workspace_path or not workspace_path.strip():
        raise ValueError("workspace_path must be a non-empty string")
    p = Path(workspace_path)
    if not p.exists():
        raise FileNotFoundError(f"Workspace path does not exist: {workspace_path}")
    if not p.is_dir():
        raise ValueError(f"Workspace path is not a directory: {workspace_path}")
    return p


def _require_workspace(workspace_path: str):
    """Return (Path, Workspace) or raise ValueError."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    p = _validate_workspace_path(workspace_path)
    return p, WorkspaceManager.open(p)


def find_workspace_root(start: Path) -> Path | None:
    """Walk up from *start* looking for a ``workspace.yaml`` marker.

    Returns the first ancestor (including *start* itself if it is a directory)
    that contains ``workspace.yaml``, or ``None``. Shared by bundles that accept
    a project/media path and need to locate the enclosing workspace root.
    """
    candidates = [start] if start.is_dir() else []
    candidates.extend(start.parents)
    for parent in candidates:
        if (parent / "workspace.yaml").exists():
            return parent
    return None


def find_source_or_latest(
    workspace_path: Path,
    source: str,
    extensions: set[str],
) -> Path | None:
    """Resolve *source* to a file path, or the newest matching file in raw.

    If *source* is non-empty it is returned as-is (absolute, or resolved under
    the workspace root) -- existence is the caller's concern. Otherwise the
    newest file in ``media/raw`` whose suffix is in *extensions* (by mtime) is
    returned, or ``None`` if the directory is absent/empty.

    Shared by the file-processing bundles (stabilize / denoise / two-pass
    normalize / ai_mask); each passes its own extension set so the intentionally
    different video-vs-media filters are preserved. Note: ``tools/audio.py``'s
    ``_find_audio_file`` is deliberately *not* routed here -- it adds an
    ``is_file()`` guard on the explicit-path branch (different behavior).
    """
    if source and source.strip():
        p = Path(source)
        if not p.is_absolute():
            p = workspace_path / source
        return p

    raw_dir = workspace_path / "media" / "raw"
    if not raw_dir.exists():
        return None
    candidates = sorted(
        (f for f in raw_dir.iterdir()
         if f.is_file() and f.suffix.lower() in extensions),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None
