"""Small looping preview generation for clips (pure functions).

Command-construction helpers for the ``clips_preview_gif`` MCP bundle tool
(``edit_mcp/server/bundles/clip_preview.py``).  Produces a tiny, fast-to-scan
preview per clip -- either a high-quality looping **GIF** (two-pass
``palettegen`` / ``paletteuse``) or a tiny **mp4** -- written under
``reports/previews/``.  Never writes to ``media/raw``.

The GIF path is two commands: pass 1 builds an optimal 256-colour palette from
the sampled window, pass 2 renders the GIF against that palette (far better
quality than a single-pass GIF).  Both passes share one ``fps=..,scale=..``
chain so the frame count is deterministic (``seconds * fps``).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

#: Preview formats this pipeline can emit.
SUPPORTED_FORMATS: frozenset[str] = frozenset({"gif", "mp4"})


def preview_output_name(source_stem: str, fmt: str) -> str:
    """Return the preview filename for a clip stem and format.

    Args:
        source_stem: Source clip filename without extension.
        fmt: ``"gif"`` or ``"mp4"``.

    Returns:
        ``"<stem>_preview.<fmt>"``.
    """
    return f"{source_stem}_preview.{fmt}"


def _vf_chain(fps: int, width: int) -> str:
    """Shared scale/fps filter chain (even height, lanczos scaling)."""
    return f"fps={fps},scale={width}:-2:flags=lanczos"


def palettegen_command(
    input_path: Path,
    palette_path: Path,
    seconds: float,
    fps: int,
    width: int,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg pass 1: generate an optimal palette from the preview window."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += [
        "-t", f"{seconds:.4f}",
        "-i", str(input_path),
        "-vf", f"{_vf_chain(fps, width)},palettegen",
        str(palette_path),
    ]
    return cmd


def paletteuse_command(
    input_path: Path,
    palette_path: Path,
    output_path: Path,
    seconds: float,
    fps: int,
    width: int,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg pass 2: render the looping GIF against the generated palette."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += [
        "-t", f"{seconds:.4f}",
        "-i", str(input_path),
        "-i", str(palette_path),
        "-lavfi", f"{_vf_chain(fps, width)}[x];[x][1:v]paletteuse",
        "-loop", "0",
        str(output_path),
    ]
    return cmd


def mp4_preview_command(
    input_path: Path,
    output_path: Path,
    seconds: float,
    fps: int,
    width: int,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg command for a tiny, muted, web-friendly mp4 preview."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += [
        "-t", f"{seconds:.4f}",
        "-i", str(input_path),
        "-an",
        "-vf", f"{_vf_chain(fps, width)}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return cmd


def expected_frame_count(seconds: float, fps: int) -> int:
    """Deterministic frame count for a preview (``round(seconds * fps)``)."""
    return max(1, seconds_to_frames(seconds, fps))
