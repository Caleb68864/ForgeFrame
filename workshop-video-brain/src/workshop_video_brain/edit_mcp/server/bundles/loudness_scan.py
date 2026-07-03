"""``audio_loudness_scan`` MCP tool -- batch loudness measurement.

Auto-imported by ``server/bundles/__init__.py``. Analysis-only: reads media and
writes a JSON report into ``reports/`` -- no snapshots, no project writes.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    iter_media_files,
    resolve_under_workspace,
    timestamp_slug,
    write_json_report,
)
from workshop_video_brain.edit_mcp.pipelines.loudness_scan import scan_loudness
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp


@mcp.tool()
def audio_loudness_scan(
    workspace_path: str,
    source_or_dir: str = "",
) -> dict:
    """Measure per-clip loudness (LUFS / true-peak / LRA) across a shoot.

    Reuses the ``loudnorm`` measure pass to build a per-clip loudness table for
    consistency sorting, and writes a JSON report to ``reports/``.

    Args:
        workspace_path: Path to workspace root.
        source_or_dir: A clip path or a directory of clips (absolute or
            workspace-relative). Empty uses ``media/raw``.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)

        if source_or_dir and source_or_dir.strip():
            target = resolve_under_workspace(ws_path, source_or_dir)
        else:
            target = ws_path / "media" / "raw"

        clips = iter_media_files(target)
        if not clips:
            return _err(f"No media files found at: {target}")

        report = scan_loudness(clips)
        report_path = write_json_report(
            ws_path, f"loudness_scan_{timestamp_slug()}.json", report
        )
        report["report_path"] = str(report_path)
        return _ok(report)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
