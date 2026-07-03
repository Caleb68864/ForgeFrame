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
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.edit_mcp.pipelines import clip_preview as _cp


def _probe_frame_geometry(path: Path) -> tuple[int | None, int | None, int | None]:
    """Return (width, height, counted_frames) for a rendered preview."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-count_frames",
                "-show_entries", "stream=width,height,nb_read_frames",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=False,
        )
        vals = out.stdout.split()
        if len(vals) >= 3:
            return int(vals[0]), int(vals[1]), int(vals[2])
        if len(vals) == 2:
            return int(vals[0]), int(vals[1]), None
    except (ValueError, OSError):
        pass
    return None, None, None


@mcp.tool()
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
            return _err("ffmpeg/ffprobe are not available on PATH.")

        ws_path = _validate_workspace_path(workspace_path)

        fmt = (format or "gif").lower()
        if fmt not in _cp.SUPPORTED_FORMATS:
            return _err(
                f"unsupported format {format!r}; expected one of "
                f"{', '.join(sorted(_cp.SUPPORTED_FORMATS))}."
            )
        if seconds <= 0:
            return _err("seconds must be positive.")
        if fps < 1:
            return _err("fps must be >= 1.")
        if width < 2:
            return _err("width must be >= 2.")

        src = Path(source)
        if not src.is_absolute():
            src = ws_path / source
        if not src.exists() or not src.is_file():
            return _err(f"source clip not found: {src}")

        previews = ws_path / "reports" / "previews"
        previews.mkdir(parents=True, exist_ok=True)
        output_path = previews / _cp.preview_output_name(src.stem, fmt)

        if fmt == "gif":
            palette = previews / f"{src.stem}_palette.png"
            pass1 = _cp.palettegen_command(src, palette, seconds, fps, width)
            p1 = subprocess.run(pass1, capture_output=True, text=True, check=False)
            if p1.returncode != 0 or not palette.exists():
                return _err(f"palettegen failed: {p1.stderr[-400:]}")
            pass2 = _cp.paletteuse_command(
                src, palette, output_path, seconds, fps, width
            )
            p2 = subprocess.run(pass2, capture_output=True, text=True, check=False)
            palette.unlink(missing_ok=True)
            if p2.returncode != 0 or not output_path.exists():
                return _err(f"paletteuse failed: {p2.stderr[-400:]}")
        else:
            cmd = _cp.mp4_preview_command(src, output_path, seconds, fps, width)
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0 or not output_path.exists():
                return _err(f"mp4 preview failed: {proc.stderr[-400:]}")

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
        return _err(str(exc))
