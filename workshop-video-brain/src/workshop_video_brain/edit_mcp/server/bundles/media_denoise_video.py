"""``media_denoise_video`` MCP tool -- one-call video denoise.

Auto-imported by ``server/bundles/__init__.py``; registers one tool on the
shared FastMCP singleton. Follows the exact shape of ``media_stabilize``:
resolve a source under the workspace, never touch ``media/raw``, write the
result into ``media/processed/``, and return an ``_ok`` / ``_err`` result dict.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.denoise_video import (
    denoise_video_file,
    denoised_output_path,
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

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}


def _find_video_file(workspace_path: Path, source: str) -> Path | None:
    """Locate a video file: explicit path or latest in ``media/raw``."""
    if source and source.strip():
        p = Path(source)
        if not p.is_absolute():
            p = workspace_path / source
        return p

    raw_dir = workspace_path / "media" / "raw"
    if not raw_dir.exists():
        return None
    candidates = sorted(
        (f for f in raw_dir.iterdir()
         if f.is_file() and f.suffix.lower() in _VIDEO_EXTS),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@mcp.tool()
@tool_guard
def media_denoise_video(
    workspace_path: str,
    source: str = "",
    strength: str = "medium",
    method: str = "hqdn3d",
    output_name: str = "",
) -> dict:
    """Clean up grainy / high-ISO / low-light footage in one call.

    Applies FFmpeg's ``hqdn3d`` (spatial + temporal) or ``atadenoise``
    (temporal) denoise and writes a new file to ``media/processed/``. The audio
    track is stream-copied so only the video is re-encoded, and the source in
    ``media/raw`` is never modified.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file. If empty, uses the latest file in
            ``media/raw/``.
        strength: ``light`` | ``medium`` | ``strong`` (default ``medium``).
            Higher removes more grain but softens detail.
        method: ``hqdn3d`` (spatial + temporal, default) or ``atadenoise``
            (adaptive temporal).
        output_name: Optional output filename. Defaults to
            ``{stem}_denoised{ext}``.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        src = _find_video_file(ws_path, source)
        if src is None:
            return _err(
                "No video file found. Provide source or add files to media/raw/."
            )
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        # Safety: never overwrite files in media/raw/.
        raw_dir = (ws_path / "media" / "raw").resolve()
        try:
            src.resolve().relative_to(raw_dir)
            src_in_raw = True
        except ValueError:
            src_in_raw = False

        processed_dir = ws_path / "media" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        output = denoised_output_path(src, processed_dir, output_name or None)
        if src_in_raw and output.resolve() == src.resolve():
            return _err(
                "Refusing to overwrite media/raw source; choose an output_name."
            )

        result = denoise_video_file(
            src,
            output,
            strength=strength,
            method=method,
        )
        if not result["success"]:
            return _err(result.get("error", "Denoise failed"))

        return _ok({
            "input": str(src),
            "output": result["final_output"],
            "method": result["method"],
            "strength": result["strength"],
            "filter": result["filter"],
            "settings": result["params"]["values"],
            "steps_count": len(result["steps"]),
        })
    except Exception as exc:  # noqa: BLE001 -- surface any failure as an error dict
        return operation_failed(str(exc), cause=exc)
