"""Thin wrappers over the ``yt-dlp`` CLI for the reaction-GIF workflow.

Two calls only: subtitles without the video (``download_subs``) and a single
time section of the video (``download_section``). Command builders are pure;
the runners shell out with a timeout.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)

SECTION_FORMAT = "bv*[height<=720]+ba/b[height<=720]/b"


class YtDlpError(RuntimeError):
    """yt-dlp exited nonzero or produced no output."""


class YtDlpNotFound(RuntimeError):
    """The yt-dlp binary is not on PATH."""


def ytdlp_binary() -> str:
    found = shutil.which("yt-dlp")
    if not found:
        raise YtDlpNotFound(
            "yt-dlp not found on PATH. Install it (e.g. 'sudo pacman -S yt-dlp' "
            "or 'pipx install yt-dlp')."
        )
    return found


def _mmss(seconds: float) -> str:
    whole = int(seconds)
    frac = seconds - whole
    text = f"{whole // 60}:{whole % 60:02d}"
    return text + (f"{frac:.3f}"[1:] if frac > 0.0005 else "")


def build_subs_command(url: str, out_template: Path, binary: str = "yt-dlp") -> list[str]:
    return [
        binary, "--write-subs", "--write-auto-subs", "--sub-langs", "en.*",
        "--convert-subs", "srt", "--skip-download", "-o", str(out_template), url,
    ]


def build_section_command(
    url: str, start: float, end: float, output: Path, binary: str = "yt-dlp"
) -> list[str]:
    return [
        binary, "-f", SECTION_FORMAT,
        "--download-sections", f"*{_mmss(start)}-{_mmss(end)}",
        "--force-keyframes-at-cuts", "--merge-output-format", "mp4",
        "-o", str(output), url,
    ]


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join([ln for ln in proc.stderr.splitlines() if ln.strip()][-8:])
        raise YtDlpError(f"yt-dlp failed (rc={proc.returncode}):\n{tail}")
    return proc


def download_subs(url: str, work_dir: Path) -> list[Path]:
    """Fetch English subs (manual and auto) as SRT into *work_dir*."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    _run(build_subs_command(url, work_dir / "subs", ytdlp_binary()), ANALYSIS_TIMEOUT_SECONDS)
    found = sorted(work_dir.glob("subs*.srt"))
    if not found:
        raise YtDlpError(f"yt-dlp found no English subtitles for {url}.")
    return found


def download_section(url: str, start: float, end: float, output: Path) -> Path:
    """Download only ``start..end`` (seconds) of *url* to *output* (mp4)."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(build_section_command(url, start, end, output, ytdlp_binary()), DEFAULT_TIMEOUT_SECONDS)
    if not output.is_file():
        raise YtDlpError(f"yt-dlp reported success but {output} was not written.")
    return output
