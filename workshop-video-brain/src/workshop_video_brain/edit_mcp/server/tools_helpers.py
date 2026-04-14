"""Shared helpers for MCP tool registrations.

Extracted from `server/tools.py` so that generated per-effect wrapper modules
(`pipelines/effect_wrappers/*.py`) can import them without importing the
giant `server.tools` module (avoiding circular imports + slow startup).

Also exposes `register_effect_wrapper` -- a decorator that applies
`@mcp.tool()` and tracks the wrapped function name in a module-level list
for traceability.
"""
from __future__ import annotations

from pathlib import Path


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
