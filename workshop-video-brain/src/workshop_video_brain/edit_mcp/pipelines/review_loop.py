"""Agent review-loop + publish-thumbnail pipeline (gap items 5a / 5b).

Two orchestration entry points power the "watch your own edit" workflow so an
agent can render, LOOK, and QC in a single call:

- :func:`render_review_frames` -- melt-render a project to a throwaway low-res
  preview (reusing the render executor + ``preview`` profile), extract frames on
  a fixed interval and/or at marker timestamps, tile them into a contact sheet
  (reusing :func:`thumbnail_sheet.grid_dimensions`), and optionally run the
  post-render QC pass (:mod:`qc_check`). Everything lands under
  ``reports/review/<timestamp>/`` so the returned frame PNGs can be Read as
  images by the caller.

- :func:`thumbnail_generate` -- pull one frame (from a media file directly, or by
  melt-rendering a single frame of a ``.kdenlive`` project) and overlay bold
  title text via PIL, matching the ``templates/titles`` style vocabulary
  (font / scale / colours / outline), producing a publish thumbnail under
  ``reports/thumbnails/``.

This module *imports* (never modifies) the render executor, thumbnail_sheet,
qc_check and titles pipelines.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
from workshop_video_brain.edit_mcp.pipelines.qc_check import run_qc as _run_qc_pipeline
from workshop_video_brain.edit_mcp.pipelines.thumbnail_sheet import grid_dimensions
from workshop_video_brain.edit_mcp.pipelines.titles import normalize_color

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure planning helpers (unit-tested)
# ---------------------------------------------------------------------------

def frame_timestamps(duration: float, every_seconds: float) -> list[float]:
    """Timestamps at ``0, every, 2*every, ...`` strictly within ``[0, duration)``.

    Raises ``ValueError`` for a non-positive interval; returns ``[]`` for a
    non-positive duration.
    """
    if every_seconds <= 0:
        raise ValueError("every_seconds must be > 0")
    if duration <= 0:
        return []
    out: list[float] = []
    t = 0.0
    while t < duration:
        out.append(round(t, 3))
        t += every_seconds
    return out


def marker_timestamps(workspace_path: Path | str) -> list[float]:
    """Sorted, unique ``start_seconds`` values from ``markers/*.json``.

    Best-effort: any file that is not a JSON list of marker dicts is skipped.
    Only entries carrying a numeric ``start_seconds`` contribute.
    """
    markers_dir = Path(workspace_path) / "markers"
    if not markers_dir.exists():
        return []
    times: set[float] = set()
    for path in sorted(markers_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("marker file unreadable %s: %s", path, exc)
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict) and "start_seconds" in item:
                try:
                    times.add(float(item["start_seconds"]))
                except (TypeError, ValueError):
                    continue
    return sorted(times)


def review_output_dir(workspace_path: Path | str, timestamp: str | None = None) -> Path:
    """Return ``reports/review/<timestamp>/`` under the workspace (not created)."""
    ts = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return Path(workspace_path) / "reports" / "review" / ts


def _titles_template_dir() -> Path:
    """Locate the repo ``templates/titles`` directory from this module."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "templates" / "titles"
        if candidate.is_dir():
            return candidate
    return here.parents[5] / "templates" / "titles"


# TitleSpec-style fields a thumbnail template YAML may set, restricted to the
# subset the PIL text overlay consumes.
_THUMBNAIL_STYLE_FIELDS = {
    "font_family",
    "title_font_size",
    "subtitle_font_size",
    "title_font_scale",
    "subtitle_font_scale",
    "font_color",
    "subtitle_color",
    "outline_color",
    "outline_width",
    "align",
    "anchor",
}


def load_thumbnail_style(style: str) -> dict:
    """Load styling overrides for *style* from ``templates/titles/<style>.yaml``.

    Mirrors the title-card style loader: only the drawing-relevant subset of the
    style vocabulary is returned. Raises ``ValueError`` for an unknown style.
    """
    import yaml

    tdir = _titles_template_dir()
    path = tdir / f"{style}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in tdir.glob("*.yaml"))
        raise ValueError(
            f"Unknown thumbnail style {style!r}. Available: {available or '(none)'}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: v for k, v in data.items() if k in _THUMBNAIL_STYLE_FIELDS}


# ---------------------------------------------------------------------------
# Render-executor plumbing
# ---------------------------------------------------------------------------

def _build_review_job(
    workspace_path: Path,
    project_path: Path,
    output_path: Path,
    log_path: Path,
) -> RenderJob:
    """Construct a preview RenderJob writing into the review directory."""
    workspace_id = uuid4()
    try:
        from workshop_video_brain.workspace.manifest import read_manifest

        workspace_id = read_manifest(workspace_path).workspace_id
    except Exception as exc:  # noqa: BLE001 -- best-effort manifest read
        # Fall back to a fresh id so a preview render can still proceed, but log
        # it: a random id breaks render<->workspace correlation, so a missing/
        # unreadable manifest should not vanish silently.
        logger.warning(
            "Could not read workspace_id from manifest at %s; using a fresh id "
            "(render/workspace correlation will be lost): %s",
            workspace_path, exc,
        )
    return RenderJob(
        workspace_id=workspace_id,
        project_path=str(project_path.resolve()),
        profile="preview",
        output_path=str(output_path),
        mode="review",
        status=JobStatus.queued,
        log_path=str(log_path),
    )


def _extract_frame(source: Path, at_seconds: float, out_png: Path, width: int) -> bool:
    """Extract a single frame from a rendered media file at *at_seconds*."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, at_seconds):.3f}",
        "-i", str(source),
        "-frames:v", "1",
        "-vf", f"scale={int(width)}:-2",
        str(out_png),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.debug("frame extract failed @%.3fs: %s", at_seconds, proc.stderr[-300:])
    return proc.returncode == 0 and out_png.exists()


# ---------------------------------------------------------------------------
# 5a -- render + look + QC
# ---------------------------------------------------------------------------

def render_review_frames(
    workspace_path: Path | str,
    project_file: str,
    every_seconds: float = 10.0,
    at_markers: bool = False,
    width: int = 640,
    run_qc: bool = True,
    keep_render: bool = False,
) -> dict:
    """Render a cut to a throwaway preview, extract review frames, and QC it.

    Returns a dict with ``success``, ``output_dir``, ``frame_paths``,
    ``sheet_path``, ``qc`` (report dict, possibly empty), ``render_path`` (str
    when *keep_render*, else ``None``), ``duration``, ``timestamps`` and
    ``frame_count``.
    """
    workspace_path = Path(workspace_path)
    project_path = Path(project_file)
    if not project_path.is_absolute():
        project_path = workspace_path / project_file
    if not project_path.exists():
        return {"success": False, "error": f"Project file not found: {project_path}"}

    out_dir = review_output_dir(workspace_path)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # 1. render preview -------------------------------------------------------
    render_path = out_dir / "preview.mp4"
    log_path = out_dir / "preview.log"
    try:
        profile = load_profile("preview")
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"could not load preview profile: {exc}"}

    job = _build_review_job(workspace_path, project_path, render_path, log_path)
    done = execute_render(job, profile)
    if str(done.status) != JobStatus.succeeded.value or not render_path.exists():
        return {
            "success": False,
            "error": "preview render failed",
            "log_path": str(log_path),
            "output_dir": str(out_dir),
        }

    # 2. duration -------------------------------------------------------------
    duration = 0.0
    try:
        duration = float(probe_media(render_path).duration or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.debug("duration probe failed: %s", exc)

    # 3. timestamps -----------------------------------------------------------
    timestamps: list[float] = []
    if every_seconds and every_seconds > 0:
        timestamps.extend(frame_timestamps(duration, every_seconds))
    if at_markers:
        for t in marker_timestamps(workspace_path):
            if 0.0 <= t < (duration or float("inf")):
                timestamps.append(round(t, 3))
    timestamps = sorted({round(t, 3) for t in timestamps})
    if not timestamps:
        timestamps = [0.0]

    # 4. extract frames -- keep frame_paths aligned with timestamps by dropping
    #    any timestamp whose seek yielded no frame (e.g. a seek past the last
    #    decodable frame near the clip end).
    frame_paths: list[str] = []
    kept_timestamps: list[float] = []
    for t in timestamps:
        fp = frames_dir / f"frame_{len(frame_paths):03d}.png"
        if _extract_frame(render_path, t, fp, width):
            frame_paths.append(str(fp))
            kept_timestamps.append(t)
    timestamps = kept_timestamps

    # 5. contact sheet (reuse thumbnail_sheet grid math) ----------------------
    sheet_path: str | None = None
    if frame_paths:
        cols, rows = grid_dimensions(len(frame_paths))
        sheet = out_dir / "sheet.png"
        scmd = [
            "ffmpeg", "-y",
            "-i", str(frames_dir / "frame_%03d.png"),
            "-vf", f"tile={cols}x{rows}",
            "-frames:v", "1",
            str(sheet),
        ]
        sproc = subprocess.run(scmd, capture_output=True, text=True)
        if sproc.returncode == 0 and sheet.exists():
            sheet_path = str(sheet)
        else:
            logger.warning("contact-sheet pass failed: %s", sproc.stderr[-300:])

    # 6. QC -------------------------------------------------------------------
    qc: dict = {}
    if run_qc:
        try:
            report = _run_qc_pipeline(render_path)
            qc = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
        except Exception as exc:  # noqa: BLE001
            qc = {"error": str(exc)}

    # 7. keep / drop the render ----------------------------------------------
    render_out: str | None = str(render_path)
    if not keep_render:
        try:
            render_path.unlink()
        except OSError:
            pass
        render_out = None

    return {
        "success": True,
        "output_dir": str(out_dir),
        "frame_paths": frame_paths,
        "sheet_path": sheet_path,
        "qc": qc,
        "render_path": render_out,
        "duration": duration,
        "timestamps": timestamps,
        "frame_count": len(frame_paths),
    }


# ---------------------------------------------------------------------------
# 5b -- publish thumbnail
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = {
    "DejaVu Sans": ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"],
    "DejaVu Serif": ["DejaVuSerif-Bold.ttf", "DejaVuSerif.ttf"],
}
_FONT_FALLBACK_PATHS = [
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(family: str, size: int):
    """Best-effort bold TrueType font for *family* at *size* px."""
    from PIL import ImageFont

    names = _FONT_CANDIDATES.get(family, []) + ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    for path in _FONT_FALLBACK_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rgba(color: str) -> tuple[int, int, int, int]:
    """Parse a style colour (``#RRGGBB[AA]`` / ``r,g,b[,a]``) to an RGBA tuple."""
    r, g, b, a = (int(x) for x in normalize_color(color).split(","))
    return (r, g, b, a)


def _render_kdenlive_frame(project_path: Path, at_seconds: float, out_png: Path) -> bool:
    """Melt-render a single project frame at *at_seconds* to *out_png*.

    Uses the composite-over-track path proven by ``test_title_renders``: render
    frames ``0..N`` and keep the last, so a title composited on a top track shows
    correctly rather than being flattened onto black.
    """
    fps = 25.0
    try:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        fps = parse_project(project_path).profile.fps or 25.0
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not read project fps, defaulting 25: %s", exc)

    frame = max(0, round(at_seconds * fps))
    tmp_dir = out_png.parent / f".mlt_{project_path.stem}_{frame}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "melt", str(project_path), f"out={frame}",
        "-consumer", f"avformat:{tmp_dir}/f_%05d.png",
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    frames = sorted(tmp_dir.glob("f_*.png"))
    if not frames:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False
    shutil.move(str(frames[-1]), str(out_png))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_png.exists()


def _extract_base_frame(src: Path, at_seconds: float, out_png: Path) -> bool:
    """Extract the base thumbnail frame from a media file or a .kdenlive project."""
    if src.suffix.lower() == ".kdenlive":
        return _render_kdenlive_frame(src, at_seconds, out_png)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, at_seconds):.3f}",
        "-i", str(src),
        "-frames:v", "1",
        str(out_png),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and out_png.exists()


def _draw_thumbnail_text(img, text: str, subtitle: str, style: dict):
    """Overlay bold title (+ optional subtitle) onto *img* using the style dict."""
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    w, h = img.width, img.height

    title_size = style.get("title_font_size") or max(
        24, round(h * float(style.get("title_font_scale", 0.13)))
    )
    sub_size = style.get("subtitle_font_size") or max(
        16, round(h * float(style.get("subtitle_font_scale", 0.06)))
    )
    family = style.get("font_family", "DejaVu Sans")
    font = _load_font(family, int(title_size))
    sub_font = _load_font(family, int(sub_size))

    fill = _rgba(style.get("font_color", "#FFFFFF"))
    sub_fill = _rgba(style.get("subtitle_color", "#FFD400"))
    outline = _rgba(style.get("outline_color", "#000000"))
    ow = int(style.get("outline_width", 8))
    align = style.get("align", "center")
    anchor = style.get("anchor", "bottom")

    margin = round(w * 0.06)
    has_sub = bool(subtitle and subtitle.strip())

    tb = draw.textbbox((0, 0), text, font=font, stroke_width=ow)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    if has_sub:
        sub_ow = max(1, ow // 2)
        sb = draw.textbbox((0, 0), subtitle, font=sub_font, stroke_width=sub_ow)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    else:
        sub_ow = 0
        sw = sh = 0
    gap = round(title_size * 0.2) if has_sub else 0
    block_h = th + gap + sh

    if anchor == "top":
        y = margin
    elif anchor == "center":
        y = round((h - block_h) / 2)
    else:  # bottom
        y = h - margin - block_h

    def x_for(text_w: int) -> int:
        if align == "left":
            return margin
        if align == "right":
            return w - margin - text_w
        return round((w - text_w) / 2)

    draw.text(
        (x_for(tw), y), text, font=font, fill=fill,
        stroke_width=ow, stroke_fill=outline,
    )
    if has_sub:
        draw.text(
            (x_for(sw), y + th + gap), subtitle, font=sub_font, fill=sub_fill,
            stroke_width=sub_ow, stroke_fill=outline,
        )
    return img


def thumbnail_generate(
    workspace_path: Path | str,
    source_or_project: str,
    at_seconds: float,
    text: str = "",
    subtitle: str = "",
    style: str = "thumbnail",
    output_name: str = "",
    width: int = 1280,
) -> dict:
    """Extract a frame and overlay bold title text to make a publish thumbnail.

    *source_or_project* may be a media file (frame pulled via ffmpeg) or a
    ``.kdenlive`` project (single frame melt-rendered). Text is drawn with PIL
    using the ``templates/titles/<style>.yaml`` vocabulary. Output PNG lands in
    ``reports/thumbnails/``.

    Returns ``success``, ``output_path``, ``width``, ``height``, ``text``,
    ``subtitle``, ``style`` and ``source``.
    """
    from PIL import Image

    workspace_path = Path(workspace_path)
    src = Path(source_or_project)
    if not src.is_absolute():
        src = workspace_path / source_or_project
    if not src.exists():
        return {"success": False, "error": f"Source not found: {src}"}

    try:
        style_data = load_thumbnail_style(style)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    out_dir = workspace_path / "reports" / "thumbnails"
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_frame = out_dir / f".raw_{src.stem}_{int(round(float(at_seconds) * 1000))}.png"
    try:
        ok = _extract_base_frame(src, float(at_seconds), tmp_frame)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"frame extraction error: {exc}"}
    if not ok:
        return {"success": False, "error": "frame extraction failed"}

    img = Image.open(tmp_frame).convert("RGBA")
    if width and img.width != int(width):
        new_h = max(1, round(img.height * (int(width) / img.width)))
        img = img.resize((int(width), new_h), Image.LANCZOS)

    if text and text.strip():
        img = _draw_thumbnail_text(img, text, subtitle, style_data)

    name = output_name or f"{src.stem}_thumb"
    if not name.lower().endswith(".png"):
        name += ".png"
    out_path = out_dir / name
    img.convert("RGB").save(out_path, "PNG")

    try:
        tmp_frame.unlink()
    except OSError:
        pass

    return {
        "success": True,
        "output_path": str(out_path),
        "width": img.width,
        "height": img.height,
        "text": text,
        "subtitle": subtitle,
        "style": style,
        "source": str(src),
    }
