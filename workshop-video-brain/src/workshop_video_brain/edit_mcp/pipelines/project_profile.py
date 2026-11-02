"""Project profile setup pipeline -- resolution, frame rate, colorspace."""
from __future__ import annotations

import logging
import math
import subprocess
from collections.abc import Iterable
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject, ProjectProfile
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegCommandError, FFmpegNotFound

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709")

VALID_COLORSPACES = {601, 709, 240}

# Known NTSC fractional rates: map float -> (num, den)
_NTSC_RATES = {
    23.976: (24000, 1001),
    23.98: (24000, 1001),
    29.97: (30000, 1001),
    59.94: (60000, 1001),
}


def set_project_profile(
    project: KdenliveProject,
    width: int,
    height: int,
    fps_num: int,
    fps_den: int,
    colorspace: int | None = None,
) -> KdenliveProject:
    """Set project profile attributes. Deep-copies project first.

    Args:
        project: Source KdenliveProject to update.
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps_num: Frame rate numerator.
        fps_den: Frame rate denominator.
        colorspace: ITU colorspace code (601, 709, or 240). Defaults to 709.

    Returns:
        A deep copy of the project with updated profile.
    """
    if colorspace is None:
        colorspace = 709
    if colorspace not in VALID_COLORSPACES:
        raise ValueError(
            f"Invalid colorspace {colorspace}; must be one of {sorted(VALID_COLORSPACES)}"
        )

    result = deepcopy(project)
    result.profile.width = width
    result.profile.height = height
    result.profile.fps = fps_num / fps_den
    result.profile.colorspace = str(colorspace)
    return result


def _fps_to_num_den(fps: float) -> tuple[int, int]:
    """Convert float fps to integer num/den pair."""
    # Check known NTSC rates first (within tolerance)
    for known_fps, (num, den) in _NTSC_RATES.items():
        if abs(fps - known_fps) < 0.01:
            return num, den

    # Integer rates
    if abs(fps - round(fps)) < 0.001:
        return int(round(fps)), 1

    # Fallback: use Fraction for exact representation
    frac = Fraction(fps).limit_denominator(1001)
    return frac.numerator, frac.denominator


def match_profile_to_source(source_path: Path) -> dict:
    """Probe source file and return recommended profile settings.

    Args:
        source_path: Path to the source media file.

    Returns:
        Dict with keys: width, height, fps_num, fps_den, colorspace (int).
    """
    asset = probe_media(source_path)
    fps_num, fps_den = _fps_to_num_den(asset.fps)
    return {
        "width": asset.width,
        "height": asset.height,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "colorspace": 709,
    }


def profile_from_media(paths: Iterable[str | Path]) -> ProjectProfile:
    """Return the profile of the first path that exists and has a usable video stream.

    Falls back to a copy of :data:`DEFAULT_PROFILE` when none qualifies, which is
    what lets a builder keep working from unresolved clip references.
    """
    for raw in paths:
        path = Path(raw) if raw else None
        if path is None or not path.is_file():
            continue
        try:
            asset = probe_media(path)
            matched = match_profile_to_source(path)
        except (FFmpegCommandError, FFmpegNotFound, subprocess.CalledProcessError, OSError, ValueError) as exc:
            logger.info("Skipping %s for the project profile: %s", path, exc)
            continue
        fps_den = matched["fps_den"]
        fps = matched["fps_num"] / fps_den if fps_den else 0.0
        if not asset.video_codec or not asset.width or not asset.height or not math.isfinite(fps) or fps <= 0:
            continue
        logger.info("Project profile taken from %s", path)
        return ProjectProfile(width=asset.width, height=asset.height, fps=fps, colorspace="709")
    return DEFAULT_PROFILE.model_copy()
