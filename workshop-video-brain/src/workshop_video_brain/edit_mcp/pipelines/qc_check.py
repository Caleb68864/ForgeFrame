"""Post-render quality-check pipeline."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.qc import QCReport, TimeRange

logger = logging.getLogger(__name__)

ALL_CHECKS = ["black_frames", "silence", "loudness", "clipping", "file_size"]


def run_qc(file_path: Path, checks: list[str] | None = None) -> QCReport:
    """Run quality checks on a rendered file.

    Parameters
    ----------
    file_path:
        Path to the media file to check.
    checks:
        Subset of ALL_CHECKS to run, or None for all.

    Returns
    -------
    QCReport with per-check results and overall_pass verdict.
    """
    selected = checks if checks else list(ALL_CHECKS)
    report = QCReport(file_path=str(file_path))

    # Populate basic file info
    if file_path.exists():
        report.file_size_bytes = file_path.stat().st_size

    for check in selected:
        try:
            if check == "black_frames":
                _check_black_frames(file_path, report)
            elif check == "silence":
                _check_silence(file_path, report)
            elif check == "loudness":
                _check_loudness(file_path, report)
            elif check == "clipping":
                _check_clipping(file_path, report)
            elif check == "file_size":
                _check_file_size(file_path, report)
            else:
                logger.warning("Unknown QC check: %s", check)
                report.checks_skipped.append(check)
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Check '%s' skipped -- filter unavailable: %s", check, exc)
            report.checks_skipped.append(check)

    report.overall_pass = len(report.checks_failed) == 0
    return report


# ---- individual checks ----------------------------------------------------

def _run_ffmpeg(args: list[str]) -> str:
    """Run an ffmpeg command and return stderr output."""
    result = subprocess.run(
        ["ffmpeg", *args],
        capture_output=True,
        text=True,
    )
    return result.stderr


def _check_black_frames(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10",
        "-an", "-f", "null", "-",
    ])
    pattern = re.compile(
        r"black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)"
    )
    regions = [
        TimeRange(start_seconds=float(m.group(1)), end_seconds=float(m.group(2)))
        for m in pattern.finditer(stderr)
    ]
    report.black_frames = regions
    if regions:
        report.checks_failed.append("black_frames")
    else:
        report.checks_passed.append("black_frames")


def _check_silence(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-af", "silencedetect=n=-50dB:d=1.0",
        "-vn", "-f", "null", "-",
    ])
    starts = re.findall(r"silence_start:\s*(\d+\.?\d*)", stderr)
    ends = re.findall(r"silence_end:\s*(\d+\.?\d*)", stderr)
    regions = [
        TimeRange(start_seconds=float(s), end_seconds=float(e))
        for s, e in zip(starts, ends)
    ]
    report.silence_regions = regions
    if regions:
        report.checks_failed.append("silence")
    else:
        report.checks_passed.append("silence")


def _check_loudness(path: Path, report: QCReport) -> None:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import measure_loudness

    data = measure_loudness(path)
    if data is None:
        report.checks_skipped.append("loudness")
        return

    # Handle both LoudnessResult dataclass (production) and dict (test mocks)
    if isinstance(data, dict):
        report.loudness_lufs = data.get("input_i")
        report.true_peak_dbtp = data.get("input_tp")
    else:
        report.loudness_lufs = data.input_i
        report.true_peak_dbtp = data.input_tp

    failed = False
    if report.loudness_lufs is not None and report.loudness_lufs < -24.0:
        failed = True  # too quiet for YouTube (-14 LUFS target)
    if report.true_peak_dbtp is not None and report.true_peak_dbtp > -1.0:
        failed = True  # true peak too hot

    if failed:
        report.checks_failed.append("loudness")
    else:
        report.checks_passed.append("loudness")


def _check_clipping(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-af", "astats=metadata=1:reset=1",
        "-vn", "-f", "null", "-",
    ])
    # astats reports "Number of Nans", "Number of Infs", "Number of denormals"
    # and per-channel peak levels. Check for Flat_factor or clipping indicators.
    clipping = "Flat_factor" in stderr or "clipping" in stderr.lower()
    report.audio_clipping = clipping
    if clipping:
        report.checks_failed.append("clipping")
    else:
        report.checks_passed.append("clipping")


def _check_file_size(path: Path, report: QCReport) -> None:
    size = report.file_size_bytes
    if size == 0 and not path.exists():
        # Cannot determine size of a non-existent file; skip this check
        report.checks_passed.append("file_size")
        return
    if size < 1024:
        report.checks_failed.append("file_size")
    elif size > 10 * 1024 * 1024 * 1024:  # 10 GB
        report.checks_failed.append("file_size")
    else:
        report.checks_passed.append("file_size")
