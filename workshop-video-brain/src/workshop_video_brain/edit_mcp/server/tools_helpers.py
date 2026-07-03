"""Shared helpers for MCP tool registrations.

Extracted from `server/tools.py` so that generated per-effect wrapper modules
(`pipelines/effect_wrappers/*.py`) can import them without importing the
giant `server.tools` module (avoiding circular imports + slow startup).

Also exposes `register_effect_wrapper` -- a decorator that applies
`@mcp.tool()` and tracks the wrapped function name in a module-level list
for traceability.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Latest-project selection (shared, version-aware)
# ---------------------------------------------------------------------------

# Matches a trailing ``_v<N>`` version suffix on a project *stem*, e.g.
# ``my-clip_v12`` -> 12.  Kdenlive working copies are written as
# ``<slug>_v<N>.kdenlive`` by the serializer.
_VERSION_SUFFIX_RE = re.compile(r"_v(\d+)$")


def _project_version_key(path: Path) -> tuple[int, int, float]:
    """Sort key used to pick the *latest* project file.

    Ordering rules (highest wins):

    - Files whose stem ends in ``_v<N>`` rank by the numeric ``N`` so that
      ``slug_v10`` beats ``slug_v2`` (the lexicographic bug this replaces).
    - Files without a numeric ``_v`` suffix fall back to modification time and
      always rank *below* any versioned file (a versioned working copy is the
      canonical edit target).
    """
    m = _VERSION_SUFFIX_RE.search(path.stem)
    if m:
        return (1, int(m.group(1)), 0.0)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (0, 0, mtime)


def latest_project(files: Iterable[Path]) -> Path | None:
    """Return the newest project path from *files*, or ``None`` if empty.

    Selection prefers the highest numeric ``_v<N>`` suffix, falling back to
    modification time for names without one.  This is the single source of
    truth for "which .kdenlive is the latest" across the whole codebase.
    """
    paths = [Path(f) for f in files]
    if not paths:
        return None
    return max(paths, key=_project_version_key)


# ---------------------------------------------------------------------------
# Response shape helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    return {"status": "success", "data": data}


def _err(message: str) -> dict:
    return {"status": "error", "message": message}


# ---------------------------------------------------------------------------
# Workspace validation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Effect wrapper registration
# ---------------------------------------------------------------------------

__wrapped_effects__: list[str] = []


def register_effect_wrapper(fn):
    """Decorator combining `@mcp.tool()` + module-level export tracking.

    Generated effect wrapper modules apply this decorator so each wrapper
    function both registers with the FastMCP singleton and appears in the
    `__wrapped_effects__` list for traceability/testing.
    """
    from workshop_video_brain.server import mcp
    __wrapped_effects__.append(fn.__name__)
    return mcp.tool()(fn)
