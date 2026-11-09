"""Post-render quality-check pipeline."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.qc import QCReport, TimeRange
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS as _ANALYSIS_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

ALL_CHECKS = ["black_frames", "silence", "loudness", "clipping", "file_size"]

# Clipping thresholds. astats prints, per channel and under "Overall", a
# ``Peak level dB`` and a ``Flat factor`` (how flat the waveform tops are,
# i.e. consecutive samples pinned at the peak). Real clipping shows both: a
# peak at or within a hair of full scale AND a non-zero flat factor. A clean
# signal that touches -0.05 dBFS once has flat factor 0 and is not flagged.
CLIP_PEAK_DB_THRESHOLD = -0.1
CLIP_FLAT_FACTOR_THRESHOLD = 0.0

_PEAK_DB_RE = re.compile(r"Peak level dB:\s*(-?inf|-?\d+(?:\.\d+)?)")
_FLAT_FACTOR_RE = re.compile(r"Flat factor:\s*(-?\d+(?:\.\d+)?)")


class QCCheckError(RuntimeError):
    """ffmpeg ran but could not analyse the file for one check.

    Typical causes: the file has no stream of the needed kind (a video-only
    render has nothing for ``silence``/``clipping``) or the file is corrupt.
    Recorded as a skip with a reason, never as a pass.
    """


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
            logger.warning("Check '%s' skipped -- ffmpeg unavailable: %s", check, exc)
            report.checks_skipped.append(check)
            report.check_errors[check] = f"ffmpeg unavailable: {exc}"
        except subprocess.TimeoutExpired as exc:
            logger.warning("Check '%s' skipped -- ffmpeg timed out after %ss", check, exc.timeout)
            report.checks_skipped.append(check)
            report.check_errors[check] = f"ffmpeg timed out after {exc.timeout}s"
        except QCCheckError as exc:
            logger.warning("Check '%s' skipped on %s: %s", check, file_path, exc)
            report.checks_skipped.append(check)
            report.check_errors[check] = str(exc)

    # A pass must mean something was verified: if every requested check was
    # skipped, nothing was checked and the report must not claim a pass.
    ran_any = bool(report.checks_passed or report.checks_failed)
    report.overall_pass = ran_any and not report.checks_failed
    logger.info(
        "QC %s: passed=%s failed=%s skipped=%s",
        file_path, report.checks_passed, report.checks_failed, report.checks_skipped,
    )
    return report


# ---- individual checks ----------------------------------------------------

def _run_ffmpeg(args: list[str]) -> str:
    """Run an ffmpeg analysis command and return its stderr.

    Raises QCCheckError on a non-zero exit. The exit code used to be ignored,
    so a corrupt file or a missing audio/video stream produced empty detector
    output and the check was reported as *passed*.
    """
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", *args]
    logger.debug("QC ffmpeg: %s", cmd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_ANALYSIS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        raise QCCheckError(
            f"ffmpeg exited {result.returncode}: " + (" | ".join(tail) or "no output")
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
    # The old check looked for the literal "Flat_factor" (a metadata key that
    # astats never prints to stderr), so it could not fire on real output.
    # Parse the numeric "Peak level dB" / "Flat factor" summary lines instead.
    peaks = [
        float("-inf") if "inf" in v else float(v)
        for v in _PEAK_DB_RE.findall(stderr)
    ]
    flats = [float(v) for v in _FLAT_FACTOR_RE.findall(stderr)]
    if not peaks:
        raise QCCheckError("astats produced no 'Peak level dB' statistics")
    peak_db = max(peaks)
    flat = max(flats) if flats else 0.0
    report.audio_peak_db = None if peak_db == float("-inf") else peak_db
    report.audio_flat_factor = flat
    clipping = peak_db >= CLIP_PEAK_DB_THRESHOLD and flat > CLIP_FLAT_FACTOR_THRESHOLD
    report.audio_clipping = clipping
    if clipping:
        report.checks_failed.append("clipping")
    else:
        report.checks_passed.append("clipping")


def _check_file_size(path: Path, report: QCReport) -> None:
    size = report.file_size_bytes
    if size == 0 and not path.exists():
        # A non-existent file is a skip, not a pass (it used to be "passed").
        report.checks_skipped.append("file_size")
        report.check_errors["file_size"] = "file does not exist"
        return
    if size < 1024:
        report.checks_failed.append("file_size")
    elif size > 10 * 1024 * 1024 * 1024:  # 10 GB
        report.checks_failed.append("file_size")
    else:
        report.checks_passed.append("file_size")
