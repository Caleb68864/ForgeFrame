"""``transcript_index`` MCP tools -- segment-level FTS5 transcript search.

Auto-imported by ``server/bundles/__init__.py``. Registers three tools that
back the SQLite FTS5 index at ``reports/transcript_index.db``:

- ``transcript_index_build`` -- (re)build the index from ``transcripts/*.json``.
- ``transcript_search`` -- BM25-ranked, timestamped segment hits.
- ``transcript_edit`` -- correct a segment in the JSON source + reindex.

Complementary to ``clips_search`` (coarse, clip-level over labels); this is the
fine-grained, jump-to-timestamp surface. The DB is a derived, rebuildable index
-- the JSON transcripts remain the source of truth.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines import transcript_index as _idx
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)


@mcp.tool()
@tool_guard
def transcript_index_build(workspace_path: str, rebuild: bool = False) -> dict:
    """Build (or incrementally update) the transcript search index.

    Walks ``transcripts/*_transcript.json`` into a SQLite FTS5 database at
    ``reports/transcript_index.db``. Incremental by file mtime: unchanged
    transcripts are skipped. Set *rebuild* to drop and fully recreate the DB.

    Args:
        workspace_path: Path to the workspace root directory.
        rebuild: If True, delete the existing DB and reindex everything.

    Returns:
        ``{clips_indexed, segments_indexed, clips_skipped, db_path}``.
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        return _ok(_idx.build_index(ws, rebuild=rebuild))
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)


@mcp.tool()
@tool_guard
def transcript_search(
    workspace_path: str,
    query: str,
    limit: int = 10,
    clip: str = "",
) -> dict:
    """Search transcript segments, BM25-ranked, with jump-to timestamps.

    Unlike ``clips_search`` (whole-clip label matching), this returns the exact
    segment + start/end seconds where the query text appears, ranked so
    exact/fuller matches come first. Auto-builds the index if it is missing.

    Args:
        workspace_path: Path to the workspace root directory.
        query: Free-text search string.
        limit: Maximum number of segment hits to return (default 10).
        clip: Optional clip_ref to restrict the search to one clip.

    Returns:
        ``{query, count, hits: [{clip, start_seconds, end_seconds, text,
        score, seg_index}]}``.
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        if not query or not query.strip():
            return invalid_input("query must be a non-empty string", suggestion="Pass a non-empty value for this argument.")
        db = _idx.index_db_path(ws)
        if not db.exists():
            _idx.build_index(ws, rebuild=False)
        hits = _idx.search(ws, query, limit=limit, clip=(clip or None))
        return _ok({"query": query, "count": len(hits), "hits": hits})
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)


@mcp.tool()
@tool_guard
def transcript_edit(
    workspace_path: str,
    clip: str,
    segment_index: int,
    new_text: str,
) -> dict:
    """Correct a mis-transcribed segment and reindex that single row.

    Writes back to ``transcripts/{clip}_transcript.json`` (the source of
    truth), marks the row as human-edited, and updates just that FTS row.

    Args:
        workspace_path: Path to the workspace root directory.
        clip: Clip reference (transcript stem, e.g. ``clip_step1``).
        segment_index: Zero-based segment ordinal within the clip.
        new_text: Corrected segment text.

    Returns:
        ``{clip, segment_index, old_text, new_text}``.
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        if not clip or not clip.strip():
            return invalid_input("clip must be a non-empty string", suggestion="Pass a non-empty value for this argument.")
        result = _idx.edit_segment(ws, clip.strip(), segment_index, new_text)
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
