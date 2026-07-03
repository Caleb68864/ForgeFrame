"""``media_slideshow`` bundle tool: timelapse/slideshow from an image folder.

Additive route (SYNTHESIS gap #9): assemble a folder of stills into a normal
H.264 clip in ``media/processed/`` via FFmpeg, after which the result is an
ordinary ingestable video.  Pure command construction lives in
``edit_mcp/pipelines/slideshow.py``; this module handles workspace/profile
resolution, FFmpeg execution and the ``_ok``/``_err`` result dicts, following
the audio-tools conventions (never touches ``media/raw``, writes to
``media/processed``).

Auto-imported by ``server/bundles/__init__.py`` so the ``@mcp.tool()``
decorator registers on import.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.edit_mcp.pipelines import slideshow as _ss

_DEFAULT_WIDTH = 1920
_DEFAULT_HEIGHT = 1080
_DEFAULT_FPS = 25.0


def _resolve_profile(
    ws_path: Path, resolution: str | None
) -> tuple[int, int, float]:
    """Resolve (width, height, fps) for the output.

    Priority: explicit *resolution* (``"WxH"``) > latest working-copy project
    profile > 1920x1080.  FPS always comes from the latest project profile when
    available, else 25.0.
    """
    width, height = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    fps = _DEFAULT_FPS

    # Try to read the latest project profile (width/height/fps).
    try:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
            parse_project,
        )
        from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project
        working = ws_path / "projects" / "working_copies"
        files = list(working.glob("*.kdenlive")) if working.exists() else []
        if files:
            proj = parse_project(latest_project(files), missing_ok=True)
            width = proj.profile.width or width
            height = proj.profile.height or height
            fps = proj.profile.fps or fps
    except Exception:
        pass

    if resolution and resolution.strip():
        raw = resolution.lower().replace(" ", "")
        if "x" not in raw:
            raise ValueError(
                f"resolution must be 'WIDTHxHEIGHT' (e.g. '1920x1080'), got {resolution!r}"
            )
        w_str, h_str = raw.split("x", 1)
        width, height = int(w_str), int(h_str)

    if width <= 0 or height <= 0:
        raise ValueError(f"invalid resolution {width}x{height}")
    if fps <= 0:
        fps = _DEFAULT_FPS
    return width, height, fps


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=False,
        )
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except (ValueError, OSError):
        return None


@mcp.tool()
def media_slideshow(
    workspace_path: str,
    image_folder: str,
    fps_per_image: float = 6.0,
    duration_per_image_seconds: float | None = None,
    resolution: str | None = None,
    output_name: str | None = None,
    kenburns: bool = False,
    crossfade_frames: int = 0,
) -> dict:
    """Assemble a folder of images into a timelapse/slideshow video clip.

    Additive route: builds a normal H.264 ``.mp4`` in ``media/processed/`` that
    can then be ingested like any other clip. Sources in ``image_folder`` are
    never modified. Scales/pads every image to the project profile.

    Args:
        workspace_path: Path to the workspace root.
        image_folder: Folder of images (absolute, or relative to the
            workspace). Non-recursive; naturally sorted by filename.
        fps_per_image: Frames each image is held for (the tutorial's
            frame-duration "ffs" field). On-screen seconds = fps_per_image /
            project_fps. Ignored when *duration_per_image_seconds* is given.
        duration_per_image_seconds: Explicit seconds-per-image (overrides
            *fps_per_image*).
        resolution: Output ``"WIDTHxHEIGHT"``. Defaults to the project profile,
            then 1920x1080.
        output_name: Output filename (``.mp4`` appended if missing). Defaults to
            ``slideshow_<folder>.mp4``.
        kenburns: Apply a simple centred slow-zoom (pan/zoom) per image.
        crossfade_frames: Dissolve length in frames between images (0 = hard
            cut). Uses ``xfade``; practical only for small sets.

    Returns:
        ``{"status": "success", "data": {...}}`` with the output path, image
        count, resolution, per-image timing, backend used and probed duration,
        or ``{"status": "error", "message": ...}``.
    """
    try:
        import shutil
        if not shutil.which("ffmpeg"):
            return _err("ffmpeg is not available on PATH.")

        ws_path = _validate_workspace_path(workspace_path)

        folder = Path(image_folder)
        if not folder.is_absolute():
            folder = ws_path / image_folder
        if not folder.exists() or not folder.is_dir():
            return _err(f"image_folder not found or not a directory: {folder}")

        images = _ss.list_images(folder)
        if not images:
            return _err(
                f"No images found in {folder} "
                f"(recognised: {', '.join(sorted(_ss.IMAGE_EXTENSIONS))})."
            )

        width, height, fps = _resolve_profile(ws_path, resolution)
        per_image_seconds = _ss.resolve_per_image_seconds(
            fps_per_image, duration_per_image_seconds, fps
        )
        crossfade_seconds = crossfade_frames / fps if crossfade_frames > 0 else 0.0

        backend = _ss.choose_backend(images, crossfade_frames, kenburns)

        if backend == "filtergraph" and len(images) > _ss.MAX_FILTERGRAPH_IMAGES:
            return _err(
                f"{len(images)} images exceeds the {_ss.MAX_FILTERGRAPH_IMAGES}-image "
                "limit for crossfade/Ken Burns/mixed-name assembly. Use a uniform "
                "numbered sequence (e.g. frame%05d.png) with no crossfade/kenburns "
                "to take the scalable pattern backend."
            )

        # Output path in media/processed (never media/raw).
        processed = ws_path / "media" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        name = output_name or f"slideshow_{folder.name}.mp4"
        if not name.lower().endswith(".mp4"):
            name = f"{name}.mp4"
        output_path = processed / name

        if backend == "pattern":
            pattern, start, _count = _ss.detect_numbered_sequence(images)
            cmd = _ss.build_pattern_command(
                folder, pattern, start, output_path,
                width, height, fps, per_image_seconds,
            )
        else:
            cmd = _ss.build_filtergraph_command(
                images, output_path, width, height, fps, per_image_seconds,
                crossfade_seconds=crossfade_seconds, kenburns=kenburns,
            )

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not output_path.exists():
            return _err(f"FFmpeg slideshow failed: {proc.stderr[-400:]}")

        expected = _ss.compute_total_duration(
            len(images), per_image_seconds, crossfade_seconds
        )
        return _ok({
            "output": str(output_path),
            "image_folder": str(folder),
            "image_count": len(images),
            "resolution": f"{width}x{height}",
            "fps": fps,
            "per_image_seconds": round(per_image_seconds, 4),
            "crossfade_frames": crossfade_frames,
            "kenburns": kenburns,
            "backend": backend,
            "expected_duration_seconds": round(expected, 3),
            "probed_duration_seconds": _probe_duration(output_path),
            "ingestable": True,
        })
    except Exception as exc:
        return _err(str(exc))
