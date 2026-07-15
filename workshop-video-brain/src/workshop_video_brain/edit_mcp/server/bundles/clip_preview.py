"""``clips_preview_gif`` bundle tool: tiny looping GIF/mp4 preview per clip.

Fast visual triage: turn a clip into a small looping GIF (two-pass
``palettegen`` / ``paletteuse`` for quality) or a tiny muted mp4, written to
``reports/previews/``.  Never touches ``media/raw`` and never overwrites the
source.  Pure command construction lives in
``edit_mcp/pipelines/clip_preview.py``.

Auto-imported by ``server/bundles/__init__.py`` so ``@mcp.tool()`` registers on
import.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_binary,
    operation_failed,
    MISSING_FILE,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.edit_mcp.pipelines import clip_preview as _cp
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_frame_geometry


# ffprobe frame-geometry probe relocated to ``adapters/ffmpeg/probe``; delegate
# kept so in-module callers resolve the same name.
_probe_frame_geometry = probe_frame_geometry


@mcp.tool()
@tool_guard
def clips_preview_gif(
    workspace_path: str,
    source: str,
    seconds: float = 3.0,
    fps: int = 8,
    width: int = 320,
    format: str = "gif",
) -> dict:
    """Generate a small looping GIF (or tiny mp4) preview of a clip.

    Renders the first *seconds* of *source* into ``reports/previews/`` for
    fast visual triage.  GIFs use a two-pass ``palettegen``/``paletteuse``
    render for quality.  The source is never modified and ``media/raw`` is
    never written.

    Args:
        workspace_path: Path to the workspace root.
        source: Source clip (absolute, or relative to the workspace).
        seconds: Preview length in seconds (from the clip start).
        fps: Preview frame rate (frames rendered = ``round(seconds * fps)``).
        width: Preview width in pixels (height auto, aspect preserved).
        format: ``"gif"`` (default) or ``"mp4"``.

    Returns:
        ``{"status":"success","data":{...}}`` with the output path, size in
        bytes, probed dimensions and frame count, or ``{"status":"error",...}``.
    """
    try:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return missing_binary("ffmpeg/ffprobe", "apt install ffmpeg (Debian/Ubuntu) or brew install ffmpeg (macOS).")

        ws_path = _validate_workspace_path(workspace_path)

        fmt = (format or "gif").lower()
        if fmt not in _cp.SUPPORTED_FORMATS:
            return err(
                f"unsupported format {format!r}; expected one of "
                f"{', '.join(sorted(_cp.SUPPORTED_FORMATS))}.",
                suggestion=f"Pass format as one of: {', '.join(sorted(_cp.SUPPORTED_FORMATS))}.",
            )
        if seconds <= 0:
            return err("seconds must be positive.", suggestion="Pass a positive seconds value for how long the preview should be.")
        if fps < 1:
            return err("fps must be >= 1.", suggestion="Pass fps as 1 or more for the preview frame rate.")
        if width < 2:
            return err("width must be >= 2.", suggestion="Pass a preview width of at least 2 pixels (e.g. 480).")

        src = Path(source)
        if not src.is_absolute():
            src = ws_path / source
        if not src.exists() or not src.is_file():
            return err(f"source clip not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it resolves under the workspace root unless absolute.", path=str(src))

        previews = ws_path / "reports" / "previews"
        previews.mkdir(parents=True, exist_ok=True)
        output_path = previews / _cp.preview_output_name(src.stem, fmt)

        if fmt == "gif":
            palette = previews / f"{src.stem}_palette.png"
            pass1 = _cp.palettegen_command(src, palette, seconds, fps, width)
            p1 = subprocess.run(pass1, capture_output=True, text=True, check=False)
            if p1.returncode != 0 or not palette.exists():
                return operation_failed("palettegen failed", cause=p1.stderr[-400:], suggestion="The external command exited non-zero; the stderr tail is in 'cause'. Check the input media/codecs and that the tool's filters are supported by your ffmpeg/melt build.")
            pass2 = _cp.paletteuse_command(
                src, palette, output_path, seconds, fps, width
            )
            p2 = subprocess.run(pass2, capture_output=True, text=True, check=False)
            palette.unlink(missing_ok=True)
            if p2.returncode != 0 or not output_path.exists():
                return operation_failed("paletteuse failed", cause=p2.stderr[-400:], suggestion="The external command exited non-zero; the stderr tail is in 'cause'. Check the input media/codecs and that the tool's filters are supported by your ffmpeg/melt build.")
        else:
            cmd = _cp.mp4_preview_command(src, output_path, seconds, fps, width)
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not output_path.exists():
                return operation_failed("mp4 preview failed", cause=proc.stderr[-400:], suggestion="The external command exited non-zero; the stderr tail is in 'cause'. Check the input media/codecs and that the tool's filters are supported by your ffmpeg/melt build.")

        pw, ph, frames = _probe_frame_geometry(output_path)
        return _ok({
            "output": str(output_path),
            "source": str(src),
            "format": fmt,
            "size_bytes": output_path.stat().st_size,
            "width": pw,
            "height": ph,
            "frame_count": frames,
            "expected_frame_count": _cp.expected_frame_count(seconds, fps),
            "seconds": seconds,
            "fps": fps,
        })
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
