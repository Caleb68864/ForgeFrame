"""Image files and burned-in watermarks, with ffmpeg only (prompt 39).

Placement uses ``image_overlay.position_rect`` so file tools and the timeline
tools (``overlay_insert`` / ``watermark_apply``) put things in the same place.
Every number in a filtergraph is formatted here; colours are validated.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegResult,
    run_ffmpeg,
)
from workshop_video_brain.edit_mcp.pipelines._common import check_unit_interval
from workshop_video_brain.edit_mcp.pipelines.audio_files import check_color
from workshop_video_brain.edit_mcp.pipelines.image_overlay import (
    POSITION_PRESETS,
    position_rect,
)
from workshop_video_brain.edit_mcp.pipelines.media_files import (
    ENCODE_VIDEO_ARGS,
    has_audio,
    require_streams,
)

IMAGE_OUT_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")
IMAGE_IN_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")
FITS = ("contain", "cover", "stretch", "pad")
MAX_SIDE = 16384


def jpeg_qscale(quality: int) -> int:
    """1-100 quality to mjpeg ``-q:v`` (2 best .. 31 worst)."""
    if not 1 <= quality <= 100:
        raise ValueError(f"quality must be 1-100, got {quality}")
    return round(2 + (100 - quality) * 29 / 100)


def format_args(ext: str, quality: int = 90) -> list[str]:
    ext = ext.lower()
    if ext not in IMAGE_OUT_EXTS:
        raise ValueError(f"unsupported image format {ext!r}; use {', '.join(IMAGE_OUT_EXTS)}")
    if ext in (".jpg", ".jpeg"):
        return ["-q:v", str(jpeg_qscale(quality))]
    if ext == ".webp":
        jpeg_qscale(quality)  # validates the range
        return ["-c:v", "libwebp", "-quality", str(int(quality))]
    return []


def is_image(path: Path, asset=None) -> bool:
    """A still image: an image extension and no duration (probe calls a PNG ``video``)."""
    if Path(path).suffix.lower() == ".svg":
        raise ValueError("SVG is not supported here (ffmpeg cannot rasterise it); export it as PNG first")
    ext = Path(path).suffix.lower()
    if ext not in IMAGE_IN_EXTS:
        return False
    if ext != ".gif":
        return True
    asset = asset or probe_media(path)
    return not asset.duration_seconds  # an animated GIF is a clip, not a still


def resize_filter(src_w: int, src_h: int, width: int, height: int, fit: str = "contain",
                  pad_color: str = "black") -> str:
    if fit not in FITS:
        raise ValueError(f"fit must be one of {', '.join(FITS)}, got {fit!r}")
    if width < 0 or height < 0 or (width == 0 and height == 0):
        raise ValueError("give a width and/or height above 0")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise ValueError(f"width/height must be at most {MAX_SIDE}")
    if not width or not height:
        return f"scale={width or -1}:{height or -1}"
    if fit == "stretch":
        return f"scale={width}:{height}"
    if fit == "cover":
        return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    contain = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
    if fit == "pad":
        return contain + f",pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={check_color(pad_color)}"
    return contain


def placement(base_w: int, base_h: int, ov_w: int, ov_h: int, position: str = "bottom_right", scale: float = 0.15,
              margin: float = 0.05, x: int = 0, y: int = 0) -> tuple[int, int, int, int]:
    aspect = ov_w / ov_h if ov_w and ov_h else None
    if position == "custom":
        w = max(1, round(base_w * scale))
        h = max(1, round(w / aspect)) if aspect else max(1, round(base_h * scale))
        return int(x), int(y), w, h
    if position not in POSITION_PRESETS:
        raise ValueError(f"position must be one of {', '.join(sorted(POSITION_PRESETS | {'custom'}))}, got {position!r}")
    return position_rect(position, base_w, base_h, scale=scale, margin=margin, aspect=aspect)


def overlay_graph(x: int, y: int, w: int, h: int, opacity: float = 1.0,
                  enable: tuple[float, float] | None = None) -> str:
    check_unit_interval("opacity", opacity)
    w, h = max(2, int(w) // 2 * 2), max(2, int(h) // 2 * 2)
    chain = f"[1:v]format=rgba,scale={w}:{h}"
    if opacity < 1.0:
        chain += f",colorchannelmixer=aa={opacity:.4f}"
    over = f"[0:v][wm]overlay={int(x)}:{int(y)}:format=auto"
    if enable is not None:
        over += f":enable='between(t,{float(enable[0]):g},{float(enable[1]):g})'"
    return f"{chain}[wm];{over}"


def resize_image(source: Path, output: Path, width: int = 0, height: int = 0, fit: str = "contain",
                 quality: int = 90, pad_color: str = "black") -> FFmpegResult:
    asset = probe_media(source)
    require_streams(asset, video=True)
    vf = resize_filter(asset.width, asset.height, width, height, fit, pad_color)
    return run_ffmpeg(["-vf", vf, "-frames:v", "1", "-update", "1", *format_args(output.suffix, quality)],
                      source, output, overwrite=True, pre_input_args=["-hide_banner"])


def convert_image(source: Path, output: Path, quality: int = 90, background: str = "") -> FFmpegResult:
    """Convert by output extension. JPEG has no alpha: ``background`` (e.g. white) fills behind it,
    else transparent areas come out black."""
    asset = probe_media(source)
    require_streams(asset, video=True)
    args = []
    if background:
        graph = f"color=c={check_color(background)}:s={asset.width}x{asset.height}[bg];[bg][0:v]overlay=shortest=1"
        args = ["-filter_complex", graph]
    args += ["-frames:v", "1", "-update", "1", *format_args(output.suffix, quality)]
    return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])


def _graph_for(base, ov, position, scale, margin, x, y, opacity, enable=None) -> str:
    px, py, pw, ph = placement(base.width, base.height, ov.width, ov.height, position, scale, margin, x, y)
    return overlay_graph(px, py, pw, ph, opacity, enable)


def overlay_image(source: Path, overlay: Path, output: Path, position: str = "bottom_right", scale: float = 0.2,
                  opacity: float = 1.0, margin: float = 0.03, x: int = 0, y: int = 0) -> FFmpegResult:
    base, ov = probe_media(source), probe_media(overlay)
    require_streams(base, video=True)
    graph = _graph_for(base, ov, position, scale, margin, x, y, opacity)
    return run_ffmpeg(["-filter_complex", graph, "-frames:v", "1", "-update", "1", *format_args(output.suffix)],
                      source, output, overwrite=True, pre_input_args=["-hide_banner"], extra_inputs=[overlay])


def watermark_video(source: Path, image: Path, output: Path, position: str = "bottom_right", scale: float = 0.15,
                    opacity: float = 0.6, margin: float = 0.03, start: float | None = None,
                    end: float | None = None) -> FFmpegResult:
    """Burn *image* into a video (re-encoded; audio copied). A single image repeats for the whole clip."""
    base, ov = probe_media(source), probe_media(image)
    require_streams(base, video=True)
    enable = None
    if start is not None or end is not None:
        enable = (start or 0.0, end if end is not None else (base.duration_seconds or 1e9))
    graph = _graph_for(base, ov, position, scale, margin, 0, 0, opacity, enable)
    args = ["-filter_complex", graph, *ENCODE_VIDEO_ARGS] + (["-c:a", "copy"] if has_audio(base) else [])
    return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"], extra_inputs=[image])
