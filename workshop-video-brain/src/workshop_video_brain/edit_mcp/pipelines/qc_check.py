"""Post-render quality-check pipeline."""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

from workshop_video_brain.core.models.qc import QCReport, TimeRange
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS as _ANALYSIS_TIMEOUT_SECONDS,
)
from workshop_video_brain.edit_mcp.pipelines.qc_scan import DEFAULTS as _QC_SCAN_DEFAULTS

logger = logging.getLogger(__name__)

# The checks run when none are named. ``profile`` is added to them whenever an
# expected profile is given; asked for by name without one, it is a skip.
ALL_CHECKS = ["black_frames", "silence", "loudness", "clipping", "file_size"]
PROFILE_CHECK = "profile"
KNOWN_CHECKS = [*ALL_CHECKS, PROFILE_CHECK]

# Silence. silencedetect still finds every run of >= 1 s under -50 dB (all are
# reported in ``silence_regions``), but a single pause is normal in a tutorial.
# The check fails only on silence that matters:
#   * any one run longer than SILENCE_MAX_RUN_SECONDS -- the "Silence > 2
#     seconds" failure the QC guide chapter documents
#     (docs/video-editing-guide/14-quality-control.md),
#   * total silence above SILENCE_MAX_RATIO of the duration -- the same
#     "mostly dead air" ratio ``clips_qc_scan`` flags (qc_scan.DEFAULTS),
#   * a run longer than SILENCE_EDGE_MAX_SECONDS at the very start or end
#     (dead air before the first word or after the last one).
SILENCE_NOISE_DB = -50.0
SILENCE_MIN_SECONDS = 1.0
SILENCE_MAX_RATIO = _QC_SCAN_DEFAULTS["silence_ratio_flag"]
SILENCE_MAX_RUN_SECONDS = 2.0
SILENCE_EDGE_MAX_SECONDS = 1.0
SILENCE_EDGE_SLACK_SECONDS = 0.05  # a run "touches" an edge within this

# Loudness. Integrated loudness is compared with a target, default YouTube's
# -14 LUFS, within +/- tolerance (docs/decisions.md 2026-11-16). 4 LU is the
# -18..-10 LUFS window the QC guide chapter already documents, and keeps the
# house ``youtube_voice`` preset (-16 LUFS) passing. True peak above -1 dBTP
# still fails on its own.
DEFAULT_TARGET_LUFS = -14.0
DEFAULT_LUFS_TOLERANCE = 4.0
TRUE_PEAK_MAX_DBTP = -1.0

# Profile. Render profiles name the encoder; ffprobe reports the codec.
_ENCODER_TO_CODEC = {
    "libx264": "h264", "h264_nvenc": "h264", "h264_vaapi": "h264", "h264_qsv": "h264",
    "libx265": "hevc", "hevc_nvenc": "hevc", "hevc_vaapi": "hevc", "hevc_qsv": "hevc",
    "prores_ks": "prores", "prores_aw": "prores",
    "libvpx-vp9": "vp9", "libvpx": "vp8",
    "libaom-av1": "av1", "libsvtav1": "av1", "librav1e": "av1",
    "dnxhd": "dnxhd", "ffv1": "ffv1", "qtrle": "qtrle",
}
PROFILE_FPS_TOLERANCE = 0.01

# Clipping thresholds. astats prints, per channel and under "Overall", a
# ``Peak level dB`` and a ``Flat factor`` (how flat the waveform tops are,
# i.e. consecutive samples pinned at the peak). Real clipping shows both: a
# peak at or within a hair of full scale AND a non-zero flat factor. A clean
# signal that touches -0.05 dBFS once has flat factor 0 and is not flagged.
CLIP_PEAK_DB_THRESHOLD = -0.1
CLIP_FLAT_FACTOR_THRESHOLD = 0.0

_PEAK_DB_RE = re.compile(r"Peak level dB:\s*(-?inf|-?\d+(?:\.\d+)?)")
_FLAT_FACTOR_RE = re.compile(r"Flat factor:\s*(-?\d+(?:\.\d+)?)")


@dataclass
class ExpectedProfile:
    """What the render should be: the chosen project or render profile.

    ``video_codec`` is an encoder name (``libx264``) or a codec name
    (``h264``); ``None`` skips the codec comparison. ``source`` says where the
    expectation came from, for the report.
    """

    width: int
    height: int
    fps: float
    video_codec: str | None = None
    source: str = ""


def expected_from_render_profile(name: str) -> ExpectedProfile:
    """The expectation a named render profile (``render_list_profiles``) sets."""
    from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

    prof = load_profile(name)
    return ExpectedProfile(
        width=prof.width, height=prof.height, fps=float(prof.frame_rate),
        video_codec=prof.video_codec, source=f"render profile {name!r}",
    )


def expected_from_project_profile(profile, source: str = "project profile") -> ExpectedProfile:
    """The expectation a Kdenlive project's profile sets (resolution and fps;
    a project profile does not choose a codec)."""
    return ExpectedProfile(
        width=int(profile.width), height=int(profile.height),
        fps=float(profile.fps), video_codec=None, source=source,
    )


class QCCheckError(RuntimeError):
    """ffmpeg ran but could not analyse the file for one check.

    Typical causes: the file has no stream of the needed kind (a video-only
    render has nothing for ``silence``/``clipping``) or the file is corrupt.
    Recorded as a skip with a reason, never as a pass.
    """


def run_qc(
    file_path: Path,
    checks: list[str] | None = None,
    *,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    lufs_tolerance: float = DEFAULT_LUFS_TOLERANCE,
    expected_profile: ExpectedProfile | None = None,
) -> QCReport:
    """Run quality checks on a rendered file.

    Parameters
    ----------
    file_path:
        Path to the media file to check.
    checks:
        Subset of KNOWN_CHECKS to run, or None for ALL_CHECKS (plus
        ``profile`` when *expected_profile* is given).
    target_lufs, lufs_tolerance:
        Integrated-loudness target and the allowed distance from it in LU.
    expected_profile:
        The profile the render should match (resolution, fps, codec).

    Returns
    -------
    QCReport with per-check results and overall_pass verdict.
    """
    if checks:
        selected = list(checks)
    else:
        selected = list(ALL_CHECKS)
        if expected_profile is not None:
            selected.append(PROFILE_CHECK)
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
                _check_loudness(file_path, report, target_lufs, lufs_tolerance)
            elif check == PROFILE_CHECK:
                _check_profile(file_path, report, expected_profile)
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


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_PROGRESS_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def _hms(match: re.Match) -> float:
    h, m, sec = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _stderr_duration(stderr: str) -> float | None:
    """The input's duration from ffmpeg's header, else the last progress time
    (the header says ``Duration: N/A`` for some inputs, e.g. raw lavfi)."""
    m = _DURATION_RE.search(stderr)
    if m:
        return _hms(m)
    times = list(_PROGRESS_TIME_RE.finditer(stderr))
    return _hms(times[-1]) if times else None


def _check_silence(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-af", f"silencedetect=n={SILENCE_NOISE_DB:g}dB:d={SILENCE_MIN_SECONDS:g}",
        "-vn", "-f", "null", "-",
    ])
    starts = [float(v) for v in re.findall(r"silence_start:\s*(-?\d+\.?\d*)", stderr)]
    ends = [float(v) for v in re.findall(r"silence_end:\s*(\d+\.?\d*)", stderr)]
    duration = _stderr_duration(stderr)
    if duration and not report.duration_seconds:
        report.duration_seconds = duration
    # A run still open at EOF has a start and no end; close it at the end.
    if duration is not None and len(starts) == len(ends) + 1:
        ends.append(duration)
    regions = [
        TimeRange(start_seconds=max(0.0, st), end_seconds=en)
        for st, en in zip(starts, ends)
    ]
    report.silence_regions = regions
    lengths = [r.end_seconds - r.start_seconds for r in regions]
    report.silence_total_seconds = round(sum(lengths), 3)
    report.silence_longest_seconds = round(max(lengths, default=0.0), 3)

    reasons: list[str] = []
    if report.silence_longest_seconds > SILENCE_MAX_RUN_SECONDS:
        reasons.append(
            f"longest silent run {report.silence_longest_seconds:.1f} s "
            f"> {SILENCE_MAX_RUN_SECONDS:g} s"
        )
    if duration and report.silence_total_seconds / duration > SILENCE_MAX_RATIO:
        reasons.append(
            f"total silence {report.silence_total_seconds:.1f} s is "
            f"{report.silence_total_seconds / duration:.0%} of {duration:.1f} s "
            f"(> {SILENCE_MAX_RATIO:.0%})"
        )
    for r, length in zip(regions, lengths):
        if length <= SILENCE_EDGE_MAX_SECONDS:
            continue
        if r.start_seconds <= SILENCE_EDGE_SLACK_SECONDS:
            reasons.append(f"{length:.1f} s of silence at the start (> {SILENCE_EDGE_MAX_SECONDS:g} s)")
        if duration and r.end_seconds >= duration - SILENCE_EDGE_SLACK_SECONDS:
            reasons.append(f"{length:.1f} s of silence at the end (> {SILENCE_EDGE_MAX_SECONDS:g} s)")

    if reasons:
        report.check_notes["silence"] = "; ".join(reasons)
        report.checks_failed.append("silence")
    else:
        if regions:
            report.check_notes["silence"] = (
                f"{len(regions)} pause(s), longest {report.silence_longest_seconds:.1f} s, "
                f"total {report.silence_total_seconds:.1f} s: within limits"
            )
        report.checks_passed.append("silence")


def _check_loudness(
    path: Path,
    report: QCReport,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    tolerance: float = DEFAULT_LUFS_TOLERANCE,
) -> None:
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

    report.loudness_target_lufs = target_lufs
    report.loudness_tolerance_lu = tolerance
    reasons: list[str] = []
    if report.loudness_lufs is not None:
        delta = report.loudness_lufs - target_lufs
        report.loudness_delta_lu = round(delta, 2)
        if abs(delta) > tolerance:
            word = "quieter" if delta < 0 else "louder"
            reasons.append(
                f"integrated {report.loudness_lufs:.1f} LUFS is {abs(delta):.1f} LU "
                f"{word} than the {target_lufs:g} LUFS target (tolerance {tolerance:g} LU)"
            )
    if report.true_peak_dbtp is not None and report.true_peak_dbtp > TRUE_PEAK_MAX_DBTP:
        reasons.append(
            f"true peak {report.true_peak_dbtp:.1f} dBTP > {TRUE_PEAK_MAX_DBTP:g} dBTP"
        )

    if reasons:
        report.check_notes["loudness"] = "; ".join(reasons)
        report.checks_failed.append("loudness")
    else:
        report.checks_passed.append("loudness")


def _codec_name(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    return _ENCODER_TO_CODEC.get(key, key)


def _check_profile(path: Path, report: QCReport, expected: ExpectedProfile | None) -> None:
    if expected is None:
        report.checks_skipped.append(PROFILE_CHECK)
        report.check_errors[PROFILE_CHECK] = (
            "no profile to compare against: pass a render profile name or a workspace"
        )
        return
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    try:
        asset = probe_media(path)
    except Exception as exc:  # noqa: BLE001 -- recorded as a skip with the cause
        raise QCCheckError(f"ffprobe could not read the render: {exc}") from exc
    if not asset.width or not asset.height:
        raise QCCheckError("the file has no video stream to compare with the profile")

    actual = {"width": asset.width, "height": asset.height,
              "fps": round(float(asset.fps), 3), "video_codec": asset.video_codec}
    report.profile_actual = actual
    report.profile_expected = asdict(expected)
    want_fps = float(Fraction(expected.fps).limit_denominator(1001)) if expected.fps else 0.0

    mismatches: list[str] = []
    if (asset.width, asset.height) != (expected.width, expected.height):
        mismatches.append(
            f"resolution {asset.width}x{asset.height}, expected {expected.width}x{expected.height}"
        )
    if abs(float(asset.fps) - want_fps) > PROFILE_FPS_TOLERANCE:
        mismatches.append(f"fps {float(asset.fps):.3f}, expected {want_fps:.3f}")
    want_codec = _codec_name(expected.video_codec)
    if want_codec and _codec_name(asset.video_codec) != want_codec:
        mismatches.append(f"codec {asset.video_codec or 'unknown'}, expected {want_codec}")

    report.profile_mismatches = mismatches
    if mismatches:
        report.check_notes[PROFILE_CHECK] = f"does not match {expected.source}: " + "; ".join(mismatches)
        report.checks_failed.append(PROFILE_CHECK)
    else:
        report.checks_passed.append(PROFILE_CHECK)


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
