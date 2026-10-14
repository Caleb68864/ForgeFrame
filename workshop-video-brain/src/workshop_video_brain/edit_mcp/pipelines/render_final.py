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
from uuid import uuid4
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    missing_media,
    missing_media_message,
)
from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    load_profile,
)

logger = logging.getLogger(__name__)

# Final renders can run for many minutes on long timelines; generous ceiling
# so a wedged ffmpeg cannot hang the server forever.
_RENDER_TIMEOUT_SECONDS = 3600.0


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
    from workshop_video_brain.edit_mcp.adapters.render.executor import check_codec_available as check
    return check(codec_name)


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

    # 3b. Same precondition the render executor enforces: melt renders footage
    # it cannot open as blank frames and still exits 0, so a project whose media
    # has moved or been deleted would otherwise produce a "successful" render
    # with shots silently missing. See adapters/render/media_check.
    absent = missing_media(project_path)
    if absent:
        raise FileNotFoundError(missing_media_message(project_path, absent))

    # 4. Build output path
    renders_dir = workspace_root / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    base_name = output_name or profile_name
    if Path(base_name).name != base_name or base_name in (".", ".."):
        raise ValueError("output_name must be a filename without directories")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = _extension_for_profile(profile)
    output_path = renders_dir / f"{base_name}_{timestamp}_{uuid4().hex[:8]}{ext}"

    # Preview and final share execution, originals swapping, and artifact tracking.
    from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render

    job = run_render(
        workspace_root, project_path, profile_name, mode="final",
        loaded_profile=profile, output_path=output_path,
        timeout_seconds=int(_RENDER_TIMEOUT_SECONDS),
    )
    if job.status != "succeeded":
        message = job.error_message or f"Render failed; see {job.log_path}"
        if job.error_type == "timeout":
            raise TimeoutError(message)
        if job.error_type == "missing_file":
            raise FileNotFoundError(message)
        raise RuntimeError(message)

    return RenderResult(
        output_path=output_path,
        profile_used=profile_name,
        duration_seconds=job.duration_seconds,
        file_size_bytes=job.file_size_bytes,
        codec_info=f"{profile.video_codec} / {profile.audio_codec}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_latest_project(workspace_root: Path) -> Path:
    """Find the latest .kdenlive project in workspace.

    Uses the shared version-aware selector (``_v<N>`` suffix, mtime fallback)
    so this agrees with every other "latest project" site in the codebase.

    Raises:
        FileNotFoundError: If no .kdenlive files found.
    """
    from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project

    kdenlive_files = list(workspace_root.rglob("*.kdenlive"))
    latest = latest_project(kdenlive_files)
    if latest is None:
        raise FileNotFoundError(
            f"No .kdenlive project found in {workspace_root}. "
            "Create a project first."
        )
    return latest


def _extension_for_profile(profile: RenderProfile) -> str:
    """Determine file extension from profile codec."""
    return f".{profile.output_extension}"

def _build_render_command(
    project_file: Path,
    output_path: Path,
    profile: RenderProfile,
) -> list[str]:
    """Build the render command for *project_file*.

    ``.kdenlive`` inputs are MLT XML: ffmpeg cannot demux them, so they are
    routed through the melt executor (``adapters/render/executor``), which
    already handles alpha/advanced consumer properties.  Direct media inputs
    (mp4/mov/...) stay on the ffmpeg re-encode path.
    """
    if Path(project_file).suffix.lower() == ".kdenlive":
        from workshop_video_brain.edit_mcp.adapters.render.executor import (
            _build_melt_command,
        )
        return _build_melt_command(Path(project_file), str(output_path), profile)

    return _build_ffmpeg_render_command(project_file, output_path, profile)


def _build_ffmpeg_render_command(
    project_file: Path,
    output_path: Path,
    profile: RenderProfile,
) -> list[str]:
    """Build an ffmpeg re-encode command for a direct-media input."""
    from workshop_video_brain.edit_mcp.adapters.render.executor import _build_ffmpeg_command
    return _build_ffmpeg_command(Path(project_file), str(output_path), profile)


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
