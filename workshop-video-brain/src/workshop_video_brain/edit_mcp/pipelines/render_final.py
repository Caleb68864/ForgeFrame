"""Full render pipeline.

Loads a named render profile, checks codec availability, finds the
latest .kdenlive project in the workspace, builds and executes an
FFmpeg command, and returns a structured RenderResult.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    list_profiles,
    load_profile,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of a successful render."""

    output_path: Path
    profile_used: str
    duration_seconds: float
    file_size_bytes: int
    codec_info: str


def check_codec_available(codec_name: str) -> bool:
    """Check if an FFmpeg encoder is available.

    Runs ``ffmpeg -codecs`` and checks for the encoder name.

    Args:
        codec_name: Encoder name, e.g. ``"libx264"``, ``"prores_ks"``.

    Returns:
        True if the encoder is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-codecs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return codec_name in result.stdout
    except Exception:
        logger.warning("Could not check codec availability", exc_info=True)
        return False


def render_final(
    workspace_root: Path,
    profile_name: str,
    output_name: str | None = None,
    project_file: str | None = None,
) -> RenderResult:
    """Execute a full render of the workspace project.

    Steps:
        1. Load the render profile by name.
        2. Check codec availability; raise if missing.
        3. Find the latest .kdenlive project in the workspace.
        4. Build FFmpeg command from profile.
        5. Execute render.
        6. Return RenderResult.

    Args:
        workspace_root: Path to workspace root.
        profile_name: Name of a render profile (e.g. "youtube-1080p").
        output_name: Optional base name for the output file. Defaults to
                     profile_name if not provided.
        project_file: Explicit path to .kdenlive project file (str). If None,
                      finds most recently modified .kdenlive in projects/working_copies/.

    Returns:
        RenderResult with output path, profile info, duration, file size.

    Raises:
        FileNotFoundError: If profile or project file is not found.
        RuntimeError: If codec is unavailable or FFmpeg fails.
    """
    # 1. Load profile
    profile = load_profile(profile_name)

    # 2. Check codec
    if not check_codec_available(profile.video_codec):
        raise RuntimeError(
            f"Encoder '{profile.video_codec}' not found. "
            f"Install FFmpeg with {profile.video_codec} support "
            f"or use a different profile."
        )

    # 3. Find .kdenlive project (explicit or auto-detect)
    if project_file is not None:
        project_path = Path(project_file)
        if not project_path.is_absolute():
            project_path = workspace_root / project_path
        if not project_path.exists():
            raise FileNotFoundError(f"Specified project file not found: {project_file}")
    else:
        project_path = _find_latest_project(workspace_root)

    # 4. Build output path
    renders_dir = workspace_root / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    base_name = output_name or profile_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = _extension_for_profile(profile)
    output_path = renders_dir / f"{base_name}_{timestamp}{ext}"

    # 5. Build and execute FFmpeg command
    cmd = _build_render_command(project_path, output_path, profile)
    logger.info("Render command: %s", " ".join(str(c) for c in cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Render failed (exit {result.returncode}): "
            f"{result.stderr[:500]}"
        )

    # 6. Gather result metadata
    file_size = output_path.stat().st_size if output_path.exists() else 0
    duration = _probe_duration(output_path) if output_path.exists() else 0.0

    return RenderResult(
        output_path=output_path,
        profile_used=profile_name,
        duration_seconds=duration,
        file_size_bytes=file_size,
        codec_info=f"{profile.video_codec} / {profile.audio_codec}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_latest_project(workspace_root: Path) -> Path:
    """Find the most recently modified .kdenlive project in workspace.

    Raises:
        FileNotFoundError: If no .kdenlive files found.
    """
    kdenlive_files = sorted(
        workspace_root.rglob("*.kdenlive"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not kdenlive_files:
        raise FileNotFoundError(
            f"No .kdenlive project found in {workspace_root}. "
            "Create a project first."
        )
    return kdenlive_files[0]


def _extension_for_profile(profile: RenderProfile) -> str:
    """Determine file extension from profile codec."""
    codec = profile.video_codec.lower()
    if "prores" in codec or "dnxh" in codec:
        return ".mov"
    return ".mp4"


def _build_render_command(
    project_file: Path,
    output_path: Path,
    profile: RenderProfile,
) -> list[str]:
    """Build FFmpeg render command from profile settings."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(project_file),
        "-vf", f"scale={profile.width}:{profile.height}",
        "-r", str(profile.fps),
        "-c:v", profile.video_codec,
        "-b:v", profile.video_bitrate,
        "-c:a", profile.audio_codec,
        "-b:a", profile.audio_bitrate,
    ]

    # Fast-start for streaming-friendly output
    if getattr(profile, "fast_start", False):
        movflags = getattr(profile, "movflags", "+faststart") or "+faststart"
        cmd.extend(["-movflags", movflags])

    # Extra args from profile
    cmd.extend(getattr(profile, "extra_args", []))

    cmd.append(str(output_path))
    return cmd


def _probe_duration(path: Path) -> float:
    """Quick ffprobe to get duration of rendered file."""
    try:
        import json
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    except Exception:
        return 0.0
