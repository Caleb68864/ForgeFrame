"""``shots_map_to_script`` MCP tool -- align build steps to clip footage.

Auto-imported by ``server/bundles/__init__.py``. Orchestrates the transcript
search index + thumbnail sheets into a step->clips coverage table so an agent
can assemble a first cut and flag reshoot gaps.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines import shot_alignment as _sa
from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    resolve_under_workspace,
)
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
def shots_map_to_script(
    workspace_path: str,
    steps_file: str,
    top_k: int = 3,
    include_thumbnails: bool = True,
) -> dict:
    """Map a numbered build-step list to candidate clips + timestamps.

    For each step, derives keywords and runs ``transcript_search`` to collect
    the top-*k* clip+timestamp candidates (BM25-ranked). When
    *include_thumbnails*, ensures a contact sheet exists per candidate clip
    (reusing the thumbnail_sheet pipeline) so the calling vision agent can
    confirm the footage. Unmatched steps are reported explicitly as coverage
    gaps for reshoots.

    Writes ``reports/shot_map.json`` and a readable ``reports/shot_map.md``.

    Args:
        workspace_path: Path to the workspace root directory.
        steps_file: Path (absolute or workspace-relative) to a markdown/text
            file of numbered build steps.
        top_k: Max candidate clips per step (default 3).
        include_thumbnails: Ensure/attach a contact sheet per candidate clip.

    Returns:
        ``{table, unmatched_steps, json_path, md_path, index,
        matched_count, step_count}``.
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        if not steps_file or not steps_file.strip():
            return err("steps_file is required.", suggestion="Pass steps_file as the path to a numbered step list; it resolves under the workspace root unless absolute.")
        steps_path = resolve_under_workspace(ws, steps_file)
        if not steps_path.exists():
            # Allow an absolute path outside the workspace too.
            alt = Path(steps_file)
            if alt.exists():
                steps_path = alt
            else:
                return err(f"Steps file not found: {steps_file}", suggestion="Check the steps_file path; it resolves under the workspace root unless absolute.")

        result = _sa.map_shots_to_script(
            ws,
            steps_path,
            top_k=top_k,
            include_thumbnails=include_thumbnails,
        )
        result["step_count"] = len(result["table"])
        result["matched_count"] = sum(
            1 for r in result["table"] if r["matched"]
        )
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
