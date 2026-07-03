"""Batch clip QC-scan pipeline (``clips_qc_scan``).

Runs a single ``-f null -`` analysis pass per clip that combines
``blackdetect`` + ``freezedetect`` + ``blurdetect`` + ``signalstats`` (video)
with ``silencedetect`` (audio), then classifies each clip as ``usable`` or
``flagged`` with human-readable reasons. Extends the ``qc_check`` pattern to
whole-shoot triage and can write an auto-rating into the b-roll index.

Empirically calibrated against FFmpeg n8.x:

* ``blackdetect`` logs ``black_start:.. black_end:..`` to stderr.
* ``freezedetect`` logs ``lavfi.freezedetect.freeze_start/freeze_end`` to stderr.
* ``silencedetect`` logs ``silence_start/silence_end`` to stderr.
* ``signalstats`` writes ``lavfi.signalstats.YAVG/YMIN/YMAX`` and
  ``blurdetect`` writes ``lavfi.blur`` -- both surfaced via the ``metadata``
  filter's ``print`` mode into a stats file.
* ``blurdetect``: **higher = blurrier** (sharp testsrc ~5, boxblurred ~31).
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

DEFAULTS = {
    "black_min": 0.5,          # min black-region seconds (blackdetect d=)
    "black_pix_th": 0.10,      # blackdetect pixel threshold
    "freeze_noise_db": -60.0,  # freezedetect noise floor (n=..dB)
    "freeze_min": 0.5,         # freezedetect min frozen seconds (d=)
    "blur_flag_threshold": 15.0,  # avg lavfi.blur above this => soft/OOF
    "yavg_min": 40.0,          # avg luma below => underexposed
    "yavg_max": 235.0,         # avg luma above => overexposed
    "silence_db": -30.0,       # silencedetect noise floor
    "silence_min": 0.6,        # silencedetect min silence seconds
    "silence_ratio_flag": 0.5,  # silence/duration above => mostly dead air
}


# ---------------------------------------------------------------------------
# Command construction (pure)
# ---------------------------------------------------------------------------

def build_video_filter(
    stats_file: Path,
    black_min: float,
    black_pix_th: float,
    freeze_noise_db: float,
    freeze_min: float,
) -> str:
    """Build the combined video-analysis filtergraph."""
    return (
        f"blackdetect=d={black_min}:pix_th={black_pix_th},"
        f"freezedetect=n={freeze_noise_db}dB:d={freeze_min},"
        f"signalstats,blurdetect,"
        f"metadata=print:file={stats_file}"
    )


def build_audio_filter(silence_db: float, silence_min: float) -> str:
    """Build the silencedetect audio filter string."""
    return f"silencedetect=noise={silence_db}dB:d={silence_min}"


def build_scan_command(
    source: Path,
    stats_file: Path,
    thresholds: dict,
) -> list[str]:
    """Build the single-pass ``-f null -`` QC command for *source*."""
    return [
        "ffmpeg", "-i", str(source),
        "-vf", build_video_filter(
            stats_file,
            thresholds["black_min"],
            thresholds["black_pix_th"],
            thresholds["freeze_noise_db"],
            thresholds["freeze_min"],
        ),
        "-af", build_audio_filter(
            thresholds["silence_db"], thresholds["silence_min"]
        ),
        "-f", "null", "-",
    ]


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------

_BLACK_RE = re.compile(r"black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)")
_FREEZE_START_RE = re.compile(r"freeze_start:\s*(\d+\.?\d*)")
_FREEZE_END_RE = re.compile(r"freeze_end:\s*(\d+\.?\d*)")
_SIL_START_RE = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_SIL_END_RE = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")
_YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=(-?\d+\.?\d*)")
_YMIN_RE = re.compile(r"lavfi\.signalstats\.YMIN=(-?\d+\.?\d*)")
_YMAX_RE = re.compile(r"lavfi\.signalstats\.YMAX=(-?\d+\.?\d*)")
_BLUR_RE = re.compile(r"lavfi\.blur=(-?\d+\.?\d*)")


def parse_black_regions(stderr: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in _BLACK_RE.findall(stderr)]


def parse_freeze_regions(stderr: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in _FREEZE_START_RE.findall(stderr)]
    ends = [float(x) for x in _FREEZE_END_RE.findall(stderr)]
    return list(zip(starts, ends))


def parse_silence_ratio(stderr: str, duration: float) -> float:
    starts = [float(x) for x in _SIL_START_RE.findall(stderr)]
    ends = [float(x) for x in _SIL_END_RE.findall(stderr)]
    total = sum(max(0.0, e - s) for s, e in zip(starts, ends))
    if duration <= 0:
        return 0.0
    return round(min(1.0, total / duration), 4)


def parse_signalstats(stats_text: str) -> dict:
    yavg = [float(x) for x in _YAVG_RE.findall(stats_text)]
    ymin = [float(x) for x in _YMIN_RE.findall(stats_text)]
    ymax = [float(x) for x in _YMAX_RE.findall(stats_text)]
    return {
        "yavg_avg": round(sum(yavg) / len(yavg), 3) if yavg else None,
        "ymin": min(ymin) if ymin else None,
        "ymax": max(ymax) if ymax else None,
    }


def parse_blur(stats_text: str) -> float | None:
    vals = [
        float(x) for x in _BLUR_RE.findall(stats_text)
        if x.lower() not in ("nan", "-nan", "inf", "-inf")
    ]
    return round(sum(vals) / len(vals), 3) if vals else None


# ---------------------------------------------------------------------------
# Classification (pure)
# ---------------------------------------------------------------------------

def classify(metrics: dict, thresholds: dict) -> tuple[str, list[str]]:
    """Return ``(verdict, reasons)`` from parsed *metrics*."""
    reasons: list[str] = []

    if metrics.get("black_regions"):
        reasons.append("black_frames")
    if metrics.get("freeze_regions"):
        reasons.append("frozen")

    blur = metrics.get("blur_avg")
    if blur is not None and blur > thresholds["blur_flag_threshold"]:
        reasons.append("blurry")

    yavg = metrics.get("yavg_avg")
    if yavg is not None:
        if yavg < thresholds["yavg_min"]:
            reasons.append("underexposed")
        elif yavg > thresholds["yavg_max"]:
            reasons.append("overexposed")

    ratio = metrics.get("silence_ratio")
    if ratio is not None and ratio > thresholds["silence_ratio_flag"]:
        reasons.append("mostly_silent")

    verdict = "flagged" if reasons else "usable"
    return verdict, reasons


def verdict_to_rating(verdict: str) -> int:
    """Map a verdict to a 0-5 b-roll rating (usable=5, flagged=1)."""
    return 5 if verdict == "usable" else 1


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _resolve_thresholds(overrides: dict | None) -> dict:
    thresholds = dict(DEFAULTS)
    if overrides:
        for k, v in overrides.items():
            if k in thresholds and v is not None:
                thresholds[k] = v
    return thresholds


def scan_clip(
    source: Path,
    thresholds: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the single-pass QC scan on one clip and return its verdict dict."""
    source = Path(source)
    th = _resolve_thresholds(thresholds)

    with tempfile.TemporaryDirectory(prefix="qcscan_") as tmp:
        stats_file = Path(tmp) / "stats.txt"
        cmd = build_scan_command(source, stats_file, th)

        if dry_run:
            return {"clip": str(source), "command": cmd, "success": True,
                    "verdict": None, "reasons": [], "metrics": {}}

        try:
            duration = probe_media(source).duration
        except Exception:  # noqa: BLE001
            duration = 0.0

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        stderr = proc.stderr
        stats_text = stats_file.read_text(encoding="utf-8") if stats_file.exists() else ""

    black = parse_black_regions(stderr)
    freeze = parse_freeze_regions(stderr)
    sig = parse_signalstats(stats_text)
    metrics = {
        "duration": round(duration, 3),
        "black_regions": len(black),
        "freeze_regions": len(freeze),
        "blur_avg": parse_blur(stats_text),
        "yavg_avg": sig["yavg_avg"],
        "ymin": sig["ymin"],
        "ymax": sig["ymax"],
        "silence_ratio": parse_silence_ratio(stderr, duration),
    }
    verdict, reasons = classify(metrics, th)

    return {
        "clip": str(source),
        "verdict": verdict,
        "reasons": reasons,
        "rating": verdict_to_rating(verdict),
        "metrics": metrics,
        "success": True,
    }


def scan_batch(
    sources: list[Path],
    thresholds: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Scan every clip in *sources* and return a batch report."""
    results = [scan_clip(s, thresholds, dry_run=dry_run) for s in sources]
    usable = sum(1 for r in results if r.get("verdict") == "usable")
    flagged = sum(1 for r in results if r.get("verdict") == "flagged")
    return {
        "clips_scanned": len(results),
        "usable": usable,
        "flagged": flagged,
        "results": results,
    }
