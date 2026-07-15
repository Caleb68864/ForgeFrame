"""``clips_detect_scenes`` MCP tool -- shot-boundary detection.

Auto-imported by ``server/bundles/__init__.py``. Analysis-only: reads media,
writes a JSON report into ``reports/`` -- no snapshots, no project writes.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    resolve_under_workspace,
    timestamp_slug,
    write_json_report,
)
from workshop_video_brain.edit_mcp.pipelines.scene_detect import detect_scenes
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    operation_failed,
    MISSING_FILE,
)


@mcp.tool()
@tool_guard
def clips_detect_scenes(
    workspace_path: str,
    source: str = "",
    threshold: float = 0.4,
) -> dict:
    """Detect shot boundaries in a long recording via ``scdet``.

    Returns a list of ``{time, score}`` cut points (score normalised to 0..1)
    and writes a JSON report to ``reports/``. Feeds ``media_segment_at_silence``
    or a manual split so each shot can land in the b-roll index.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file (absolute or workspace-relative).
        threshold: Scene-change sensitivity, 0..1 (default 0.4). Lower detects
            more, subtler cuts.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        if not source or not source.strip():
            return err("source is required.", suggestion="Pass source as the path to a video file; it resolves under the workspace root unless absolute.")
        src = resolve_under_workspace(ws_path, source)
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        result = detect_scenes(src, threshold=threshold)
        if not result.get("success"):
            return error_from_pipeline_result(
                result, "Scene detection failed", path=str(src),
            )
        report_path = write_json_report(
            ws_path, f"scenes_{src.stem}_{timestamp_slug()}.json", result
        )
        result["report_path"] = str(report_path)
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
