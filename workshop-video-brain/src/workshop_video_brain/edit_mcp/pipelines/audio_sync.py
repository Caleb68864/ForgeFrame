"""Audio-based clip synchronization -- recover the time offset between two
recordings of the same event (multicam angles, a lav mic vs camera audio).

This is the buildable core of the multicam workflow (phase A in
``docs/research/2026-07-03-tutorial-effect-analysis/multicam.md``): given two
files that captured the same sound, find how far apart they start so the clips
can be stacked in perfect sync on the timeline.

Two methods are provided:

* ``correlate`` (default, always available) -- decode a low-rate mono energy
  envelope from each file with FFmpeg, then cross-correlate the two envelopes
  and read the lag at the correlation peak. Pure NumPy; no third-party audio
  libraries. This is the method the empirical test exercises.
* ``chromaprint`` -- use FFmpeg's ``chromaprint`` muxer to emit an
  AcoustID-compatible acoustic fingerprint of each file and correlate the raw
  fingerprint streams (see ``vault/Research/FFmpeg for Video Production
  Automation.md`` §"Audio fingerprint for multicam sync"). Only usable when the
  local FFmpeg build ships the ``chromaprint`` muxer; otherwise the caller gets
  an actionable error telling them to install ``libchromaprint`` or use
  ``correlate``.

Offset convention
-----------------
``offset_seconds`` is the start of ``source_b`` **relative to** ``source_a``:
a positive value means a given event appears ``offset_seconds`` *later* into
``source_b`` than into ``source_a`` (i.e. ``source_b`` has that much extra
lead-in / started rolling earlier). To lay both on one timeline you would push
``source_b`` left by ``offset_seconds`` (or ``source_a`` right by the same).
"""
from __future__ import annotations

import functools
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Decode/analysis defaults.  8 kHz mono is plenty for envelope alignment and
# keeps the decoded buffer small; a 100 Hz envelope gives 10 ms resolution
# before sub-frame (parabolic) refinement.
DEFAULT_SAMPLE_RATE = 8_000
DEFAULT_ENVELOPE_HZ = 100
DEFAULT_WINDOW_SECONDS = 120

# Chromaprint's raw item rate: the default algorithm resamples to 11025 Hz and
# emits one 32-bit sub-fingerprint per ``4096/3`` input samples.  Used only to
# turn a fingerprint-item lag back into seconds.
_CHROMAPRINT_ITEM_HZ = 11025.0 / (4096.0 / 3.0)  # ~8.0757 items/sec


@dataclass
class SyncResult:
    """Outcome of an audio-sync estimate."""

    offset_seconds: float
    confidence: float
    method: str
    lag_units: float          # peak lag in envelope frames / fingerprint items
    unit_hz: float            # frames-per-second of the correlated series
    samples_a: int            # length of series A (frames / items)
    samples_b: int            # length of series B

    def as_dict(self) -> dict:
        return {
            "offset_seconds": round(self.offset_seconds, 4),
            "confidence": round(self.confidence, 4),
            "method": self.method,
            "lag_units": round(self.lag_units, 3),
            "unit_hz": round(self.unit_hz, 4),
            "series_len_a": self.samples_a,
            "series_len_b": self.samples_b,
        }


# ---------------------------------------------------------------------------
# FFmpeg availability probes
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def ffmpeg_available() -> bool:
    """True if an ``ffmpeg`` binary is callable."""
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-version"],
            capture_output=True,
            check=False,
        )
        return True
    except (OSError, ValueError):
        return False


@functools.lru_cache(maxsize=1)
def chromaprint_available() -> bool:
    """True if the local FFmpeg build exposes the ``chromaprint`` muxer.

    Mirrors ``ffmpeg -muxers | grep chromaprint``; result is cached.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-muxers"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return False
    return "chromaprint" in proc.stdout


# ---------------------------------------------------------------------------
# Envelope extraction (pure math is split out for unit testing)
# ---------------------------------------------------------------------------

def decode_mono_pcm(
    path: Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    window_seconds: float | None = DEFAULT_WINDOW_SECONDS,
) -> np.ndarray:
    """Decode a file to a mono float32 waveform in ``[-1, 1]`` via FFmpeg.

    Reads at most ``window_seconds`` of audio (``None`` => whole file) at
    ``sample_rate`` Hz, signed 16-bit, piped to stdout.  Raises on failure.
    """
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if window_seconds is not None and window_seconds > 0:
        cmd += ["-t", str(float(window_seconds))]
    cmd += [
        "-i", str(path),
        "-vn",
        "-ac", "1",
        "-ar", str(int(sample_rate)),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(
            f"ffmpeg audio decode failed for {path}: "
            f"{tail[-1] if tail else 'unknown error'}"
        )
    if not proc.stdout:
        raise RuntimeError(f"no decodable audio in {path}")
    samples = np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32)
    return samples / 32768.0


def energy_envelope(
    samples: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    envelope_hz: int = DEFAULT_ENVELOPE_HZ,
) -> np.ndarray:
    """Short-time RMS energy envelope at ``envelope_hz`` frames per second.

    Frames the waveform into non-overlapping ``sample_rate / envelope_hz``
    hops and takes the RMS of each.  Pure NumPy; deterministic.
    """
    samples = np.asarray(samples, dtype=np.float32)
    hop = max(1, int(round(sample_rate / envelope_hz)))
    n_frames = samples.size // hop
    if n_frames < 1:
        # Signal shorter than one hop: a single RMS value.
        return np.array([float(np.sqrt(np.mean(samples**2)))]) if samples.size else np.array([0.0])
    trimmed = samples[: n_frames * hop].reshape(n_frames, hop)
    return np.sqrt(np.mean(trimmed**2, axis=1)).astype(np.float64)


def onset_envelope(env: np.ndarray) -> np.ndarray:
    """Half-wave-rectified first difference of an envelope (onset strength).

    Emphasises attacks/transients, which give a sharper correlation peak than
    raw energy when aligning percussive or burst-like content.
    """
    env = np.asarray(env, dtype=np.float64)
    diff = np.diff(env, prepend=env[:1])
    return np.clip(diff, 0.0, None)


# ---------------------------------------------------------------------------
# Cross-correlation (the alignment math)
# ---------------------------------------------------------------------------

def _normalize(series: np.ndarray) -> np.ndarray:
    """Zero-mean, unit-L2-norm a 1-D series (returns zeros if it is flat)."""
    series = np.asarray(series, dtype=np.float64)
    series = series - series.mean()
    norm = np.linalg.norm(series)
    if norm == 0.0:
        return series
    return series / norm


def _parabolic_refine(corr: np.ndarray, peak: int) -> float:
    """Sub-sample peak position via 3-point parabolic interpolation.

    Returns a fractional offset in ``[-0.5, 0.5]`` to add to ``peak``.
    """
    if peak <= 0 or peak >= corr.size - 1:
        return 0.0
    left, mid, right = corr[peak - 1], corr[peak], corr[peak + 1]
    denom = left - 2.0 * mid + right
    if denom == 0.0:
        return 0.0
    return 0.5 * (left - right) / denom


def cross_correlate_lag(ref: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    """Estimate the lag of ``target`` relative to ``ref`` (in frames).

    Returns ``(lag_frames, confidence)`` where a positive ``lag_frames`` means
    ``target`` is ``ref`` *delayed* -- ``target[n] ~= ref[n - lag]``.  The
    ``confidence`` is the normalized cross-correlation coefficient at the peak,
    in ``[0, 1]`` (clamped).
    """
    a = _normalize(ref)
    b = _normalize(target)
    if a.size == 0 or b.size == 0 or not np.any(a) or not np.any(b):
        return 0.0, 0.0

    # Full linear cross-correlation.  corr indexed by lags in
    # [-(len_b-1) .. (len_a-1)]; value at lag L = sum_n a[n]*b[n-L].
    corr = np.correlate(a, b, mode="full")
    lags = np.arange(-(b.size - 1), a.size)
    peak_idx = int(np.argmax(corr))
    frac = _parabolic_refine(corr, peak_idx)
    lag_at_peak = lags[peak_idx] + frac

    # target[n] = ref[n-D] peaks at lag L=-D, so delay D = -L.
    delay_frames = -lag_at_peak
    confidence = float(np.clip(corr[peak_idx], 0.0, 1.0))
    return float(delay_frames), confidence


# ---------------------------------------------------------------------------
# Chromaprint route
# ---------------------------------------------------------------------------

def chromaprint_raw(
    path: Path,
    window_seconds: float | None = DEFAULT_WINDOW_SECONDS,
) -> np.ndarray:
    """Emit a file's raw chromaprint fingerprint as a uint32 array.

    Requires the ``chromaprint`` muxer; raises RuntimeError otherwise.
    """
    if not chromaprint_available():
        raise RuntimeError(
            "ffmpeg 'chromaprint' muxer not available in this build "
            "(install libchromaprint / a chromaprint-enabled ffmpeg)"
        )
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if window_seconds is not None and window_seconds > 0:
        cmd += ["-t", str(float(window_seconds))]
    cmd += [
        "-i", str(path),
        "-vn",
        "-f", "chromaprint",
        "-fp_format", "raw",
        "-silence_threshold", "-1",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(
            f"ffmpeg chromaprint fingerprint failed for {path}: "
            f"{tail[-1] if tail else 'unknown error'}"
        )
    # Raw format: newline-separated decimal uint32 items on some builds, a
    # packed little-endian uint32 stream on others.  Handle both.
    text = proc.stdout.decode("ascii", "ignore").strip()
    tokens = [t for t in text.replace(",", " ").split() if t.lstrip("-").isdigit()]
    if tokens:
        return np.array([int(t) & 0xFFFFFFFF for t in tokens], dtype=np.uint32)
    trimmed = proc.stdout[: (len(proc.stdout) // 4) * 4]
    return np.frombuffer(trimmed, dtype="<u4").copy()


def _fingerprint_bit_agreement(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Correlate two uint32 fingerprint streams by bit-agreement over lags.

    Returns ``(lag_items, confidence)`` where ``lag_items`` is the delay of
    ``b`` relative to ``a`` in fingerprint items and ``confidence`` in ``[0, 1]``
    is the best mean per-bit agreement (0.5 == chance for 32-bit words).
    """
    a = np.asarray(a, dtype=np.uint32)
    b = np.asarray(b, dtype=np.uint32)
    if a.size == 0 or b.size == 0:
        return 0.0, 0.0

    max_lag = min(a.size, b.size) - 1
    best_score = -1.0
    best_lag = 0
    # Positive L means b is delayed relative to a (b[n] == a[n-L]): shift b left
    # by L, i.e. line up a[0:] with b[L:].  Matches cross_correlate_lag's sign.
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            xa, xb = a[: b.size - lag], b[lag:]
        else:
            xa, xb = a[-lag:], b[: a.size + lag]
        n = min(xa.size, xb.size)
        if n < 8:
            continue
        xor = np.bitwise_xor(xa[:n], xb[:n]).astype(np.uint32)
        # Population count of each 32-bit XOR word.
        bits = np.unpackbits(xor.view(np.uint8)).reshape(n, 32).sum(axis=1)
        agreement = 1.0 - (bits.mean() / 32.0)
        if agreement > best_score:
            best_score = agreement
            best_lag = lag
    # Rescale chance (0.5) -> 0 confidence, perfect (1.0) -> 1.0.
    confidence = float(np.clip((best_score - 0.5) / 0.5, 0.0, 1.0))
    return float(best_lag), confidence


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def sync_by_audio(
    source_a: Path,
    source_b: Path,
    method: str = "correlate",
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    envelope_hz: int = DEFAULT_ENVELOPE_HZ,
    use_onset: bool = True,
) -> dict:
    """Recover the time offset between two recordings of the same event.

    Args:
        source_a: Reference recording.
        source_b: Second recording of the same event.
        method: ``"correlate"`` (envelope cross-correlation) or
            ``"chromaprint"`` (FFmpeg acoustic fingerprint).
        window_seconds: Analyse at most this many leading seconds of each file.
        sample_rate: PCM decode rate for the ``correlate`` method.
        envelope_hz: Envelope frame rate for the ``correlate`` method.
        use_onset: Correlate onset strength (sharper peak) rather than raw
            energy.  ``correlate`` method only.

    Returns:
        A plain dict: ``{"success": bool, ...}``.  On success carries
        ``offset_seconds`` and ``confidence`` (see module docstring for the
        sign convention).  On failure carries ``error``.
    """
    source_a = Path(source_a)
    source_b = Path(source_b)
    method = (method or "correlate").lower()

    if not ffmpeg_available():
        return {"success": False, "error": "ffmpeg not found on PATH", "method": method}
    for src in (source_a, source_b):
        if not src.exists():
            return {"success": False, "error": f"File not found: {src}", "method": method}

    try:
        if method == "correlate":
            result = _sync_correlate(
                source_a, source_b, window_seconds, sample_rate, envelope_hz, use_onset
            )
        elif method == "chromaprint":
            if not chromaprint_available():
                return {
                    "success": False,
                    "method": "chromaprint",
                    "error": (
                        "ffmpeg 'chromaprint' muxer is not available in this build. "
                        "Install a chromaprint-enabled ffmpeg (libchromaprint) or call "
                        "with method='correlate'."
                    ),
                }
            result = _sync_chromaprint(source_a, source_b, window_seconds)
        else:
            return {
                "success": False,
                "method": method,
                "error": f"Unknown method {method!r}; use 'correlate' or 'chromaprint'.",
            }
    except Exception as exc:  # noqa: BLE001 -- surface as an error dict
        return {"success": False, "method": method, "error": str(exc)}

    data = result.as_dict()
    data["success"] = True
    data["source_a"] = str(source_a)
    data["source_b"] = str(source_b)
    data["window_seconds"] = window_seconds
    return data


def _sync_correlate(
    source_a: Path,
    source_b: Path,
    window_seconds: float,
    sample_rate: int,
    envelope_hz: int,
    use_onset: bool,
) -> SyncResult:
    wav_a = decode_mono_pcm(source_a, sample_rate, window_seconds)
    wav_b = decode_mono_pcm(source_b, sample_rate, window_seconds)
    env_a = energy_envelope(wav_a, sample_rate, envelope_hz)
    env_b = energy_envelope(wav_b, sample_rate, envelope_hz)
    if use_onset:
        env_a = onset_envelope(env_a)
        env_b = onset_envelope(env_b)
    lag_frames, confidence = cross_correlate_lag(env_a, env_b)
    return SyncResult(
        offset_seconds=lag_frames / float(envelope_hz),
        confidence=confidence,
        method="correlate",
        lag_units=lag_frames,
        unit_hz=float(envelope_hz),
        samples_a=int(env_a.size),
        samples_b=int(env_b.size),
    )


def _sync_chromaprint(
    source_a: Path,
    source_b: Path,
    window_seconds: float,
) -> SyncResult:
    fp_a = chromaprint_raw(source_a, window_seconds)
    fp_b = chromaprint_raw(source_b, window_seconds)
    lag_items, confidence = _fingerprint_bit_agreement(fp_a, fp_b)
    return SyncResult(
        offset_seconds=lag_items / _CHROMAPRINT_ITEM_HZ,
        confidence=confidence,
        method="chromaprint",
        lag_units=lag_items,
        unit_hz=_CHROMAPRINT_ITEM_HZ,
        samples_a=int(fp_a.size),
        samples_b=int(fp_b.size),
    )
