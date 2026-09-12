"""VFR detection and CFR transcode pipeline.

Scans workspace video files for variable frame rate (VFR) media and
provides a transcode function to convert to constant frame rate (CFR).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    probe_media,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    DEFAULT_TIMEOUT_SECONDS as _RENDER_TIMEOUT_SECONDS,
    FFmpegCommandError,
    FFmpegResult,
    run_ffmpeg,
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


class TranscodeSourceUnreadable(RuntimeError):
    """Determined: the source is not something ffprobe can read as media.

    A file the user handed in that is not decodable video is not a defect in
    this tool, and must never be reported with the "unexpected error, please
    report it" voice.
    """


class TranscodeOutputUnwritable(RuntimeError):
    """Determined: the destination cannot be written (missing or read-only
    directory, read-only existing output). Also the user's to fix."""


class TranscodeFailed(RuntimeError):
    """**Undetermined**: ffmpeg exited non-zero and this code could not work out
    why. The source probes as readable and the destination is writable, so the
    only lead is ffmpeg's own last output, which the message carries.

    This is the honest end of the classification, and it is deliberately the
    only place a "this might be a bug" suggestion is allowed.
    """


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
        TranscodeSourceUnreadable: the source is not decodable media.
        TranscodeOutputUnwritable: the destination cannot be written.
        TranscodeFailed: ffmpeg failed for a reason this code could not
            determine; the message carries ffmpeg's own last output.
        FFmpegNotFound / FFmpegTimeout: raised through ``run_ffmpeg`` -- an
            absent binary and a wall-clock kill are already classified by the
            error contract and must not be re-labelled here.
    """
    source = Path(source)
    if target_fps is None:
        try:
            asset = probe_media(source)
        except FFmpegCommandError as exc:
            # ffprobe ran and refused the file. That is a determination, not a
            # guess: the input is the problem and there is nothing to transcode.
            raise TranscodeSourceUnreadable(
                f"{source} could not be read as video. {_one_line(str(exc))}"
            ) from exc
        target_fps = int(round(asset.fps)) or 30

    # Build output path with _cfr suffix
    output = source.parent / f"{source.stem}_cfr{source.suffix}"

    # Through ``run_ffmpeg`` rather than a hand-rolled ``subprocess.run``: it is
    # the one place that turns an absent binary into ``FFmpegNotFound`` and a
    # wall-clock kill into ``FFmpegTimeout`` (both already classified by the
    # error contract), and the one place that refuses to clobber an existing
    # file under media/raw/ or projects/source/.
    #
    # -fps_mode, not -vsync: -vsync was deprecated in ffmpeg 5.1 and removed in
    # 8.0 ("Unrecognized option 'vsync'"). -hide_banner keeps the ~1.5 KB
    # version banner out of stderr so a failure reports ffmpeg's actual error.
    result = run_ffmpeg(
        args=["-fps_mode", "cfr", "-r", str(target_fps), "-c:a", "copy"],
        input_path=source,
        output_path=output,
        overwrite=True,
        pre_input_args=["-hide_banner"],
        timeout=_RENDER_TIMEOUT_SECONDS,
    )
    if result.success:
        return output

    raise _diagnose_transcode_failure(source, output, result)


def _diagnose_transcode_failure(
    source: Path, output: Path, result: FFmpegResult
) -> RuntimeError:
    """Work out what a non-zero ffmpeg exit means -- or admit that it does not.

    This is a **post-mortem**, never a precondition: it runs only after ffmpeg
    has already failed, so it cannot refuse a transcode that would have worked.

    It also never reads ffmpeg's stderr to decide *what kind* of failure this
    was. ``adapters/render/media_check`` already made that argument against
    melt and it holds here: the wording is not part of the tool's API, it
    varies by version and build, and a match on it is a taxonomy invented from
    guesses. Each verdict below is instead something this code establishes for
    itself -- ffprobe either reads the source or it does not; the destination
    either accepts a write or it does not. ffmpeg's own words are carried into
    every message, because they are the best lead even when they cannot be
    classified.
    """
    # Flattened to ONE line on purpose: the error contract renders an
    # exception's first line as ``cause`` (``errors._one_line_cause``), so a
    # multi-line tail would be silently truncated to "ffmpeg said:" and the
    # actual reason -- the only thing that makes these errors actionable --
    # would never reach the caller.
    tail = _one_line(result.stderr_tail) or "(ffmpeg produced no output)"

    if _source_is_readable(source) is False:
        return TranscodeSourceUnreadable(
            f"{source} is not readable as video, so there is nothing to "
            f"transcode. ffmpeg said: {tail}"
        )

    destination = _destination_problem(output)
    if destination is not None:
        return TranscodeOutputUnwritable(f"{destination} ffmpeg said: {tail}")

    return TranscodeFailed(
        f"ffmpeg failed on {source.name} and the cause could not be "
        f"determined. ffmpeg said: {tail}"
    )


def _one_line(text: str) -> str:
    """Collapse a multi-line stderr tail into one ``|``-separated line."""
    return " | ".join(ln.strip() for ln in (text or "").splitlines() if ln.strip())


def _source_is_readable(path: Path) -> bool | None:
    """``True`` / ``False`` / ``None`` when it cannot be established.

    The third state matters: if ffprobe is itself missing or times out, we have
    learned nothing about the file, and saying "your media is unreadable" would
    be a guess dressed as a finding.
    """
    try:
        probe_media(path)
    except FileNotFoundError:
        return False
    except FFmpegCommandError:
        return False
    except Exception:  # FFmpegNotFound, FFmpegTimeout, bad JSON, ...
        return None
    return True


def _destination_problem(output: Path) -> str | None:
    """A one-line reason the output cannot be written, or ``None``."""
    parent = output.parent
    if not parent.is_dir():
        return f"The output directory does not exist: {parent}."
    if not os.access(parent, os.W_OK):
        return f"The output directory is not writable: {parent}."
    if output.exists() and not os.access(output, os.W_OK):
        return f"The output file already exists and is not writable: {output}."
    return None


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
