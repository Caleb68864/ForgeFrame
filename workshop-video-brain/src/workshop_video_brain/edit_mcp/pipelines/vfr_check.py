"""VFR detection and CFR transcode pipeline.

Scans workspace video files for variable frame rate (VFR) media and
provides a transcode function to convert to constant frame rate (CFR).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    DEFAULT_EXTENSIONS,
    probe_media,
)

logger = logging.getLogger(__name__)

# Only scan video extensions (exclude audio-only)
_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".mts", ".m2ts",
}


@dataclass
class VFRFile:
    """A single file identified as VFR."""

    path: str  # str for MCP serialization compatibility
    r_frame_rate: str
    avg_frame_rate: str
    divergence_pct: float


@dataclass
class VFRReport:
    """Result of scanning a workspace for VFR media."""

    files_checked: int
    vfr_files: list[VFRFile] = field(default_factory=list)
    all_cfr: bool = True


def check_vfr(workspace_root: Path) -> VFRReport:
    """Scan all video files in workspace and report VFR files.

    Args:
        workspace_root: Path to workspace root directory.

    Returns:
        VFRReport with counts and list of VFR files.
    """
    video_files = _find_video_files(workspace_root)
    vfr_files: list[VFRFile] = []
    checked = 0

    for vf in video_files:
        try:
            asset = probe_media(vf)
            checked += 1

            if asset.is_vfr:
                # Calculate divergence for the report
                r_rate = getattr(asset, "r_frame_rate", "0/1")
                avg_rate = getattr(asset, "avg_frame_rate", "0/1")
                divergence = _calculate_divergence(r_rate, avg_rate)

                vfr_files.append(VFRFile(
                    path=str(vf),
                    r_frame_rate=r_rate,
                    avg_frame_rate=avg_rate,
                    divergence_pct=divergence,
                ))
        except Exception:
            logger.warning("Failed to probe %s, skipping", vf, exc_info=True)

    return VFRReport(
        files_checked=checked,
        vfr_files=vfr_files,
        all_cfr=len(vfr_files) == 0,
    )


def transcode_to_cfr(
    source: Path,
    target_fps: int | None = None,
) -> Path:
    """Transcode a VFR file to constant frame rate.

    Args:
        source: Path to the VFR source file.
        target_fps: Target FPS. If None, auto-detect from avg_frame_rate via probe.

    Returns:
        Path to the output CFR file (alongside source with _cfr suffix).

    Raises:
        RuntimeError: If FFmpeg transcode fails.
    """
    if target_fps is None:
        asset = probe_media(source)
        target_fps = int(round(asset.fps)) or 30

    # Build output path with _cfr suffix
    output = source.parent / f"{source.stem}_cfr{source.suffix}"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(source),
        "-vsync", "cfr",
        "-r", str(target_fps),
        "-c:a", "copy",
        str(output),
    ]

    logger.info("Transcoding VFR -> CFR: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg transcode failed (exit {result.returncode}): "
            f"{result.stderr[:500]}"
        )

    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_video_files(workspace_root: Path) -> list[Path]:
    """Recursively find video files in workspace."""
    files: list[Path] = []
    for ext in _VIDEO_EXTENSIONS:
        files.extend(workspace_root.rglob(f"*{ext}"))
    return sorted(files)


def _calculate_divergence(r_frame_rate: str, avg_frame_rate: str) -> float:
    """Calculate percentage divergence between two frame rate strings."""
    r_val = _parse_rate(r_frame_rate)
    avg_val = _parse_rate(avg_frame_rate)

    if avg_val == 0:
        return 0.0

    return abs(r_val - avg_val) / avg_val * 100.0


def _parse_rate(rate_str: str) -> float:
    """Parse a frame rate string like '30/1' or '30000/1001' to float."""
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            return float(num) / float(den)
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0
