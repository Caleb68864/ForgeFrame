"""Image files (resize, convert, overlay) and a burned-in video watermark, without a workspace.

ffmpeg only; placement shared with the timeline tools (``overlay_insert``,
``watermark_apply``) through ``image_overlay.position_rect``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.server.bundles._media_shell import (
    ffmpeg_ok_or_error,
    source_path,
)
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    media_unreadable,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.server import mcp

_POSITIONS = "top_left, top_right, bottom_left, bottom_right, center, full or custom (with x, y)"


def _summary(path: Path, **extra) -> dict:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    asset = probe_media(path)
    return {"output_path": str(path), "width": asset.width, "height": asset.height,
            "size_bytes": path.stat().st_size, **extra}


def _run(src, *, suffix, ext, output_path, output_dir, overwrite, run, what, need_image=True):
    from workshop_video_brain.edit_mcp.pipelines.image_files import is_image
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output

    try:
        if need_image and not is_image(src):
            return None, invalid_input(f"{src.name} is not a still image",
                                       "For a video use media_watermark (or media_convert / media_reframe).")
        out = resolve_output(src, output_path, output_dir, suffix=suffix, ext=ext, overwrite=overwrite)
        result = run(out)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return None, media_unreadable(str(src), exc)
        return None, invalid_input(str(exc), f"Positions: {_POSITIONS}; fit contain|cover|stretch|pad; "
                                             "colours 0xRRGGBB or a name; quality 1-100.")
    problem = ffmpeg_ok_or_error(result, out, what)
    return out, problem


@mcp.tool()
@tool_guard
def image_resize(source: str, width: int = 0, height: int = 0, fit: str = "contain", quality: int = 90,
                 pad_color: str = "black", output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Resize an image. One of width/height keeps the aspect; both use ``fit``: contain (inside the
    box), cover (fill and crop), stretch, or pad (contain on ``pad_color``). Default output
    ``<name>_<W>x<H>``."""
    from workshop_video_brain.edit_mcp.pipelines.image_files import resize_image

    src = source_path(source)
    if isinstance(src, dict):
        return src
    out, problem = _run(src, suffix="_resizing", ext=None, output_path=output_path, output_dir=output_dir,
                        overwrite=True if not output_path else overwrite, what="Resize",
                        run=lambda o: resize_image(src, o, width, height, fit, quality, pad_color))
    if problem:
        return problem
    if not output_path:  # name it after the size it really came out at
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
        asset = probe_media(out)
        final = out.with_name(f"{src.stem}_{asset.width}x{asset.height}{out.suffix}")
        if final.exists() and not overwrite:
            out.unlink(missing_ok=True)
            return invalid_input(f"The output already exists: {final}. Pass overwrite=true to replace it.",
                                 "Pass overwrite=true or an output_path.")
        out = out.replace(final)
    return _ok(_summary(out, source=str(src), fit=fit))


@mcp.tool()
@tool_guard
def image_convert(source: str, format: str = "webp", quality: int = 90, background: str = "", output_path: str = "",
                  output_dir: str = "", overwrite: bool = False) -> dict:
    """Convert an image to png, jpg, webp, bmp or tiff (``output_path``'s extension wins). JPEG has
    no transparency: pass ``background`` (e.g. white) or transparent areas turn black."""
    from workshop_video_brain.edit_mcp.pipelines.image_files import convert_image

    src = source_path(source)
    if isinstance(src, dict):
        return src
    ext = Path(output_path).suffix if output_path else "." + format.lstrip(".")
    out, problem = _run(src, suffix="_converted" if ext.lower() == src.suffix.lower() else "", ext=ext,
                        output_path=output_path, output_dir=output_dir, overwrite=overwrite, what="Conversion",
                        run=lambda o: convert_image(src, o, quality, background))
    return problem or _ok(_summary(out, source=str(src)))


@mcp.tool()
@tool_guard
def image_overlay(source: str, overlay: str, position: str = "bottom_right", scale: float = 0.2, opacity: float = 1.0,
                  margin: float = 0.03, x: int = 0, y: int = 0, output_path: str = "", output_dir: str = "",
                  overwrite: bool = False) -> dict:
    """Place ``overlay`` (a logo, keeps its transparency) on an image: ``position`` preset, ``scale``
    of the width, ``opacity`` 0-1, ``margin`` from the edges; ``custom`` uses ``x``/``y``."""
    from workshop_video_brain.edit_mcp.pipelines.image_files import overlay_image

    src = source_path(source)
    if isinstance(src, dict):
        return src
    ov = source_path(overlay, "overlay")
    if isinstance(ov, dict):
        return ov
    out, problem = _run(src, suffix="_overlay", ext=None, output_path=output_path, output_dir=output_dir,
                        overwrite=overwrite, what="Overlay",
                        run=lambda o: overlay_image(src, ov, o, position, scale, opacity, margin, x, y))
    return problem or _ok(_summary(out, source=str(src), position=position))


@mcp.tool()
@tool_guard
def media_watermark(source: str, image: str, position: str = "bottom_right", scale: float = 0.15, opacity: float = 0.6,
                    margin: float = 0.03, start_seconds: float = -1.0, end_seconds: float = -1.0,
                    output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Burn a logo/watermark image into a video file (re-encoded; audio copied), for the whole clip or
    ``start_seconds``-``end_seconds``. For an editable watermark on a timeline use ``watermark_apply``.
    Default output ``<name>_wm<ext>``."""
    from workshop_video_brain.edit_mcp.pipelines.image_files import (
        is_image,
        watermark_video,
    )
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary

    src = source_path(source)
    if isinstance(src, dict):
        return src
    img = source_path(image, "image")
    if isinstance(img, dict):
        return img
    try:
        if is_image(src):
            return invalid_input(f"{src.name} is an image, not a video", "Use image_overlay for images.")
    except ValueError as exc:
        return invalid_input(str(exc), "Use a video source.")
    out, problem = _run(src, suffix="_wm", ext=None, output_path=output_path, output_dir=output_dir,
                        overwrite=overwrite, what="Watermark", need_image=False,
                        run=lambda o: watermark_video(src, img, o, position, scale, opacity, margin,
                                                      start_seconds if start_seconds >= 0 else None,
                                                      end_seconds if end_seconds >= 0 else None))
    return problem or _ok({**output_summary(out), "source": str(src), "position": position})
