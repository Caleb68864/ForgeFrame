"""Shared helpers for MCP tool registrations.

Extracted from `server/tools.py` so that generated per-effect wrapper modules
(`pipelines/effect_wrappers/*.py`) can import them without importing the
giant `server.tools` module (avoiding circular imports + slow startup).

Also exposes `register_effect_wrapper` -- a decorator that applies
`@mcp.tool()` and tracks the wrapped function name in a module-level list
for traceability.

This module is now a **package** split by domain
(`_responses`, `_workspace`, `_projects`, `_effects`, `_xml`).  This
``__init__`` is a byte-stable re-export shim: it re-exports every public *and*
private name external code imports, so all ~80 call sites (server/tools/*,
server/bundles/*, generated effect wrappers, tests) keep importing from
``...server.tools_helpers`` unchanged.  The id-normalizing ``_build_filter_xml``
builder was relocated into ``pipelines/_common`` and is re-exported here.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.server.tools_helpers._responses import (
    _ok,
    _err,
)
from workshop_video_brain.edit_mcp.server.tools_helpers._workspace import (
    _validate_workspace_path,
    _require_workspace,
    find_workspace_root,
    find_source_or_latest,
)
from workshop_video_brain.edit_mcp.server.tools_helpers._projects import (
    _VERSION_SUFFIX_RE,
    _project_version_key,
    latest_project,
    _get_video_playlists,
    _load_latest_project,
    _save_patched,
    _resolve_playlist,
)
from workshop_video_brain.edit_mcp.server.tools_helpers._effects import (
    __wrapped_effects__,
    register_effect_wrapper,
    apply_simple_effect,
    _lookup_catalog_by_service,
)
from workshop_video_brain.edit_mcp.server.tools_helpers._xml import (
    _build_filter_xml,
    _VALID_COLOR_FORMATS_MSG,
)

__all__ = [
    # _responses
    "_ok",
    "_err",
    # _workspace
    "_validate_workspace_path",
    "_require_workspace",
    "find_workspace_root",
    "find_source_or_latest",
    # _projects
    "_VERSION_SUFFIX_RE",
    "_project_version_key",
    "latest_project",
    "_get_video_playlists",
    "_load_latest_project",
    "_save_patched",
    "_resolve_playlist",
    # _effects
    "__wrapped_effects__",
    "register_effect_wrapper",
    "apply_simple_effect",
    "_lookup_catalog_by_service",
    # _xml
    "_build_filter_xml",
    "_VALID_COLOR_FORMATS_MSG",
]
