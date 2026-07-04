"""B-roll suggestion and library tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
)





# ---------------------------------------------------------------------------
# B-Roll tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def broll_suggest(workspace_path: str) -> dict:
    """Analyze transcript and suggest specific B-roll shots.

    Scans all transcript files in the workspace, detects visual description
    patterns, and returns categorised B-roll shot suggestions with timestamps,
    descriptions, and confidence scores.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Suggestions grouped by category with total count and formatted markdown.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.production_brain.skills.broll import extract_and_format

        markdown, suggestions = extract_and_format(ws_path)
        by_category: dict[str, int] = {}
        for s in suggestions:
            by_category[s["category"]] = by_category.get(s["category"], 0) + 1
        return _ok({
            "suggestions": suggestions,
            "count": len(suggestions),
            "by_category": by_category,
            "markdown": markdown,
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# B-Roll Library tools
# ---------------------------------------------------------------------------
def _resolve_broll_vault() -> Path | None:
    """Resolve vault_path for B-roll library tools."""
    from workshop_video_brain.edit_mcp.pipelines.broll_library import _resolve_vault_path
    return _resolve_vault_path()


@mcp.tool()
@tool_guard
def broll_library_index(workspace_path: str = "") -> dict:
    """Add clips from a project to the B-roll library.

    If no workspace_path is specified, index all projects under the configured
    projects root.

    Args:
        workspace_path: Optional absolute path to a project workspace. If empty,
            indexes all projects.

    Returns:
        Summary with added, skipped, and total clip counts.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.broll_library import (
            index_project,
            index_all_projects,
        )

        vault = _resolve_broll_vault()
        if vault is None:
            return err(
                "Vault path not configured.",
                suggestion="Set the WVB_VAULT_PATH environment variable to your vault, or run 'wvb init' to configure it.",
            )

        if workspace_path and workspace_path.strip():
            ws = Path(workspace_path)
            if not ws.exists():
                return missing_file(workspace_path, "Workspace path")
            result = index_project(vault, ws)
        else:
            # Index all projects
            import json as _json
            config_path = Path.home() / ".forgeframe" / "config.json"
            if not config_path.exists():
                return err(
                    "No workspace_path was provided and no ~/.forgeframe/config.json exists to fall back on.",
                    suggestion="Pass workspace_path explicitly, or run 'wvb init' to create ~/.forgeframe/config.json with your projects_root.",
                )
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            projects_root = cfg.get("projects_root", "")
            if not projects_root:
                return err("projects_root is not set in ~/.forgeframe/config.json.", suggestion="Add a \"projects_root\" entry to ~/.forgeframe/config.json, or pass workspace_path directly.")
            result = index_all_projects(vault, Path(projects_root))

        return _ok(result)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def broll_library_search(
    query: str,
    content_type: str = "",
    shot_type: str = "",
    min_rating: int = 0,
) -> dict:
    """Search the B-roll library across all projects.

    Args:
        query: Text to match against tags, topics, and description.
        content_type: Optional filter by content type (e.g. 'b_roll', 'closeup').
        shot_type: Optional filter by shot type.
        min_rating: Optional minimum rating filter (0 = no filter).

    Returns:
        List of matching BRollEntry objects sorted by relevance.
    """
    try:
        if not query or not query.strip():
            return invalid_input("query must be a non-empty string", "Pass a non-empty search term to match against B-roll tags, topics, and descriptions.", param="query")
        from workshop_video_brain.edit_mcp.pipelines.broll_library import search_library

        vault = _resolve_broll_vault()
        if vault is None:
            return invalid_input(
                "Vault path not configured. Set WVB_VAULT_PATH env var or run 'wvb init'.",
                "Set the WVB_VAULT_PATH environment variable to your Obsidian vault, or run 'wvb init' to configure it.",
            )

        filters: dict = {}
        if content_type:
            filters["content_type"] = content_type
        if shot_type:
            filters["shot_type"] = shot_type
        if min_rating > 0:
            filters["min_rating"] = min_rating

        results = search_library(vault, query, filters)
        return _ok({
            "results": [r.model_dump() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def broll_library_tag(
    source_path: str,
    tags: str = "",
    rating: int = -1,
    description: str = "",
) -> dict:
    """Add tags, rating, or description to a B-roll clip in the library.

    If the clip is not already in the library, it will be added as a minimal entry.
    Tags are merged with any existing tags (not replaced).

    Args:
        source_path: Absolute path to the media file.
        tags: Comma-separated tags to add.
        rating: Rating 0-5 (-1 = no change).
        description: Optional description to set.

    Returns:
        Updated BRollEntry data.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.broll_library import tag_clip

        vault = _resolve_broll_vault()
        if vault is None:
            return err(
                "Vault path not configured.",
                suggestion="Set the WVB_VAULT_PATH environment variable to your vault, or run 'wvb init' to configure it.",
            )

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        entry = tag_clip(vault, source_path, tags=tag_list, rating=rating, description=description)
        return _ok(entry.model_dump())
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def broll_library_stats() -> dict:
    """Get B-roll library statistics.

    Returns:
        Stats including total clips, projects indexed, top tags,
        and content type breakdown.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.broll_library import get_library_stats

        vault = _resolve_broll_vault()
        if vault is None:
            return err(
                "Vault path not configured.",
                suggestion="Set the WVB_VAULT_PATH environment variable to your vault, or run 'wvb init' to configure it.",
            )

        stats = get_library_stats(vault)
        return _ok(stats)
    except Exception as exc:
        return from_exception(exc)
