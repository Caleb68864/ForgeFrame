"""``mlt_services`` and ``mlt_service_info`` MCP tools -- what MLT can load on this host.

Auto-imported by ``server/bundles/__init__.py``. Read-only. They take no workspace,
because they describe the host rather than a project.
"""
from __future__ import annotations

import difflib

from workshop_video_brain.edit_mcp.adapters.mlt import registry as mlt_registry
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    missing_binary,
    not_found,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.server import mcp

_INSTALL_HINT = "Install MLT's melt, or your distro's python3-mlt, to list services."


def _kind_error(kind: str) -> dict | None:
    if kind in mlt_registry.KINDS:
        return None
    return invalid_input(f"Unknown kind '{kind}'.", suggestion=f"Pass kind as one of: {', '.join(mlt_registry.KINDS)}.")


@mcp.tool()
@tool_guard
def mlt_services(kind: str = "filters", query: str = "", limit: int = 200) -> dict:
    """List the MLT services this host can load.

    Args:
        kind: "filters", "transitions", "producers", "consumers" or "links".
        query: Case-insensitive substring to filter names by.
        limit: Most names to return.
    """
    problem = _kind_error(kind)
    if problem:
        return problem
    if limit <= 0:
        return invalid_input("limit must be > 0.", suggestion="Try the default, 200.")
    registry = mlt_registry.get_registry()
    if registry is None:
        return missing_binary("melt", _INSTALL_HINT)
    needle = query.strip().lower()
    names = sorted(name for name in registry.services.get(kind, ()) if needle in name.lower())
    return _ok({
        "engine": registry.engine,
        "mlt_version": registry.mlt_version,
        "kind": kind,
        "count": len(names),
        "names": [
            {"name": name, "kdenlive_unsupported": name in mlt_registry.KDENLIVE_UNSUPPORTED}
            for name in names[:limit]
        ],
    })


@mcp.tool()
@tool_guard
def mlt_service_info(kind: str, name: str) -> dict:
    """Return MLT's metadata for one service, including its parameters, as YAML.

    Args:
        kind: "filters", "transitions", "producers", "consumers" or "links".
        name: Service name, such as "avfilter.eq".
    """
    problem = _kind_error(kind)
    if problem:
        return problem
    registry = mlt_registry.get_registry()
    if registry is None:
        return missing_binary("melt", _INSTALL_HINT)
    if not registry.has(kind, name):
        close = difflib.get_close_matches(name, sorted(registry.services.get(kind, ())), n=3, cutoff=0.6)
        return not_found("MLT service", name, hint=f"Close matches: {', '.join(close)}" if close else None)
    return _ok({
        "kind": kind,
        "name": name,
        "yaml": mlt_registry.service_info(kind, name),
        "kdenlive_substitute": mlt_registry.KDENLIVE_UNSUPPORTED.get(name),
    })
