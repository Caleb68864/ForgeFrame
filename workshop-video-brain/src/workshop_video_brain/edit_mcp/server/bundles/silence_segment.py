"""``media_segment_at_silence`` MCP tool -- silence-based take splitting.

Auto-imported by ``server/bundles/__init__.py``. Segments a long recording into
per-take files via the stream-copy ``segment`` muxer, writing ONLY into
``media/processed/<stem>_takes/`` -- never ``media/raw``. No snapshots (no
project files touched).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    resolve_under_workspace,
)
from workshop_video_brain.edit_mcp.pipelines.silence_segment import (
    segment_at_silence,
    takes_dir,
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
def media_segment_at_silence(
    workspace_path: str,
    source: str = "",
    noise_db: float = -30.0,
    min_silence: float = 0.6,
    min_segment: float = 2.0,
) -> dict:
    """Split a long recording into per-take files at detected silences.

    Detects silence via the ``silencedetect`` adapter, cuts at each silence
    midpoint using the ``segment`` muxer with stream copy (no re-encode), and
    writes the takes into ``media/processed/<stem>_takes/``.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the recording (absolute or workspace-relative).
        noise_db: Silence noise floor in dBFS (default -30).
        min_silence: Minimum silence-gap seconds to cut on (default 0.6).
        min_segment: Minimum resulting segment length in seconds (default 2.0).
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        if not source or not source.strip():
            return _err("source is required (path to a recording).")
        src = resolve_under_workspace(ws_path, source)
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        out_dir = takes_dir(ws_path, src)

        # Safety: output must live under media/processed, never media/raw.
        raw_dir = (ws_path / "media" / "raw").resolve()
        if str(out_dir.resolve()).startswith(str(raw_dir)):
            return _err("Refusing to write takes into media/raw.")

        result = segment_at_silence(
            src, out_dir,
            noise_db=noise_db,
            min_silence=min_silence,
            min_segment=min_segment,
        )
        if not result["success"]:
            return _err(result.get("error", "Segmenting failed"))

        return _ok({
            "input": str(src),
            "output_dir": result["output_dir"],
            "segment_paths": result["segment_paths"],
            "segment_count": result["segment_count"],
            "cut_points": result["cut_points"],
            "silence_count": result["silence_count"],
        })
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
