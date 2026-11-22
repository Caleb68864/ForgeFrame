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


def _seek(start: float) -> list[str]:
    """Input seek before the first ``-i`` (nothing at 0, so old argv stay identical)."""
    return ["-ss", f"{start:.4f}"] if start > 0 else []


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
    start: float = 0.0,
) -> list[str]:
    """FFmpeg pass 1: generate an optimal palette from the preview window."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += _seek(start)
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
    start: float = 0.0,
) -> list[str]:
    """FFmpeg pass 2: render the looping GIF against the generated palette."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += _seek(start)
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
    start: float = 0.0,
) -> list[str]:
    """FFmpeg command for a tiny, muted, web-friendly mp4 preview."""
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += _seek(start)
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


def webp_preview_command(
    input_path: Path,
    output_path: Path,
    seconds: float,
    fps: int,
    width: int,
    overwrite: bool = True,
    start: float = 0.0,
) -> list[str]:
    """Single-pass animated WebP (loops forever)."""
    cmd = ["ffmpeg"] + (["-y"] if overwrite else []) + _seek(start)
    cmd += ["-t", f"{seconds:.4f}", "-i", str(input_path), "-an", "-vf", _vf_chain(fps, width),
            "-c:v", "libwebp_anim", "-loop", "0", "-q:v", "70", str(output_path)]
    return cmd


def render_gif_file(source: Path, output: Path, start: float, seconds: float, fps: int, width: int,
                    fmt: str = "gif") -> dict:
    """A looping GIF (two-pass palette) or WebP of ``[start, start + seconds)`` of *source*."""
    import subprocess
    import tempfile

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_frame_geometry, probe_media
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import DEFAULT_TIMEOUT_SECONDS, FFmpegNotFound

    if seconds <= 0 or not 1 <= fps <= 50 or width < 2 or start < 0:
        raise ValueError("need seconds > 0, fps 1-50, width >= 2 and start >= 0")
    if fmt not in ("gif", "webp"):
        raise ValueError(f"format must be gif or webp, got {fmt!r}")
    asset = probe_media(source)
    if not asset.width:
        raise ValueError(f"source has no video stream: {source}")
    total = asset.duration_seconds or 0.0
    if total:
        if start >= total:
            raise ValueError(f"start {start:.3f}s is past the end of the source ({total:.3f}s)")
        seconds = min(seconds, total - start)

    def run(cmd: list[str]):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=DEFAULT_TIMEOUT_SECONDS)
        except FileNotFoundError as exc:
            raise FFmpegNotFound("ffmpeg binary not found on PATH") from exc

    if fmt == "gif":
        with tempfile.TemporaryDirectory(prefix="wvb_gif_") as tmp:
            palette = Path(tmp) / "palette.png"
            proc = run(palettegen_command(source, palette, seconds, fps, width, start=start))
            if proc.returncode == 0:
                proc = run(paletteuse_command(source, palette, output, seconds, fps, width, start=start))
    else:
        proc = run(webp_preview_command(source, output, seconds, fps, width, start=start))
    tail = "\n".join([line for line in (proc.stderr or "").splitlines() if line.strip()][-10:])
    result = {"success": proc.returncode == 0 and output.exists(), "stderr_tail": tail,
              "expected_frame_count": expected_frame_count(seconds, fps), "seconds": seconds}
    if result["success"]:
        w, h, frames = probe_frame_geometry(output)
        result.update(width=w, height=h, frame_count=frames)
    return result
