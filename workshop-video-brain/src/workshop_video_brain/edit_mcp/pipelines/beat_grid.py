"""Music beat-grid pipeline: pure-NumPy onset + tempo detection.

Decodes a music track to a mono energy envelope (reusing ``audio_sync``'s FFmpeg
decode), derives an onset-strength signal (half-wave-rectified energy
derivative -- a spectral-flux-style novelty function on the energy band), peak-
picks onsets, estimates tempo by autocorrelating the onset envelope, and lays a
regular beat grid phase-locked to the detected onsets.

No third-party audio libraries (``librosa`` is deliberately NOT a dependency);
everything is NumPy on top of the shared FFmpeg PCM decode.

Outputs ``{bpm_estimate, beats:[seconds...], onsets:[seconds...]}`` -- beats are
the inferred metronome grid, onsets are the raw detected attacks.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from workshop_video_brain.edit_mcp.pipelines.audio_sync import (
    decode_mono_pcm,
    energy_envelope,
    onset_envelope,
)

# Envelope frame rate for beat analysis: 200 Hz => 5 ms resolution, ample for
# a +/-50 ms beat tolerance even before parabolic refinement.
DEFAULT_ENVELOPE_HZ = 200
DEFAULT_SAMPLE_RATE = 22_050

# Plausible tempo search band for autocorrelation.
MIN_BPM = 40.0
MAX_BPM = 240.0


# ---------------------------------------------------------------------------
# Onset peak-picking
# ---------------------------------------------------------------------------

def detect_onset_peaks(
    strength: np.ndarray,
    envelope_hz: float,
    sensitivity: float = 0.5,
) -> list[float]:
    """Peak-pick onset times (seconds) from an onset-strength envelope.

    A frame is an onset if it is a strict local maximum, exceeds an adaptive
    threshold (``mean + k*std`` where ``k`` shrinks as *sensitivity* rises), and
    is the strongest peak within a short refractory window.  Returns onset times
    in seconds, ascending.
    """
    strength = np.asarray(strength, dtype=np.float64)
    n = strength.size
    if n < 3 or not np.any(strength):
        return []

    sens = min(max(float(sensitivity), 0.0), 1.0)
    # sensitivity 0 -> k=2.0 (few onsets); 1 -> k=0.0 (many); 0.5 -> k=1.0.
    k = (1.0 - sens) * 2.0
    threshold = strength.mean() + k * strength.std()

    # Refractory window: never two onsets closer than ~120 ms.
    refractory = max(1, int(round(0.12 * envelope_hz)))

    peaks: list[int] = []
    i = 1
    while i < n - 1:
        v = strength[i]
        if v > threshold and v >= strength[i - 1] and v > strength[i + 1]:
            # Take the local argmax within the refractory window.
            lo = i
            hi = min(n, i + refractory)
            local = lo + int(np.argmax(strength[lo:hi]))
            peaks.append(local)
            i = local + refractory
        else:
            i += 1

    return [round(p / float(envelope_hz), 4) for p in peaks]


# ---------------------------------------------------------------------------
# Tempo via autocorrelation
# ---------------------------------------------------------------------------

def _parabolic_peak(y: np.ndarray, i: int) -> float:
    """Sub-sample peak offset in [-0.5, 0.5] via 3-point parabola around ``i``."""
    if i <= 0 or i >= y.size - 1:
        return 0.0
    left, mid, right = y[i - 1], y[i], y[i + 1]
    denom = left - 2.0 * mid + right
    if denom == 0.0:
        return 0.0
    return 0.5 * (left - right) / denom


def _local_argmax(acf: np.ndarray, lag: int, radius: int = 3) -> tuple[int, float]:
    """Return ``(index, value)`` of the peak within +/-``radius`` frames of ``lag``."""
    lo = max(0, lag - radius)
    hi = min(acf.size, lag + radius + 1)
    if hi <= lo:
        return lag, 0.0
    rel = int(np.argmax(acf[lo:hi]))
    idx = lo + rel
    return idx, float(acf[idx])


def _prefer_faster_octave(
    acf: np.ndarray,
    peak: int,
    min_lag: int,
    ratio: float = 0.5,
) -> int:
    """Walk ``peak`` down to a sub-multiple lag while a strong peak remains there.

    If the autocorrelation near ``peak / n`` (n = 2, 3) is at least ``ratio``
    times the value at ``peak``, the true tempo is faster -- snap to that
    sub-multiple's local peak.  Iterates so 4x/6x errors collapse too.
    """
    best = peak
    _, base = _local_argmax(acf, best)
    changed = True
    while changed:
        changed = False
        for div in (2, 3):
            cand = int(round(best / div))
            if cand < min_lag:
                continue
            idx, val = _local_argmax(acf, cand)
            if val >= ratio * base:
                best = idx
                base = val
                changed = True
                break
    return best


def estimate_tempo(
    strength: np.ndarray,
    envelope_hz: float,
    min_bpm: float = MIN_BPM,
    max_bpm: float = MAX_BPM,
) -> tuple[float, float]:
    """Estimate ``(bpm, period_seconds)`` by autocorrelating onset strength.

    Autocorrelates the zero-mean onset-strength envelope and picks the lag with
    the strongest correlation inside the ``[min_bpm, max_bpm]`` band, refined to
    sub-frame precision.  Returns ``(0.0, 0.0)`` when no tempo is recoverable.
    """
    strength = np.asarray(strength, dtype=np.float64)
    if strength.size < 4 or not np.any(strength):
        return 0.0, 0.0

    x = strength - strength.mean()
    full = np.correlate(x, x, mode="full")
    acf = full[full.size // 2:]  # non-negative lags, acf[0] == energy
    if acf[0] <= 0:
        return 0.0, 0.0

    min_lag = max(1, int(np.floor(60.0 * envelope_hz / max_bpm)))
    max_lag = int(np.ceil(60.0 * envelope_hz / min_bpm))
    max_lag = min(max_lag, acf.size - 2)
    if max_lag <= min_lag:
        return 0.0, 0.0

    band = acf[min_lag:max_lag + 1]
    rel = int(np.argmax(band))
    peak = min_lag + rel

    # Octave correction: an impulse train autocorrelates just as strongly at
    # integer multiples of its true period, and rounding can even make a
    # multiple win.  Prefer the fastest tempo whose sub-multiple lag still
    # carries a comparable peak (standard beat-tracker half-tempo guard).
    peak = _prefer_faster_octave(acf, peak, min_lag)

    refined = peak + _parabolic_peak(acf, peak)
    if refined <= 0:
        return 0.0, 0.0

    period_seconds = refined / float(envelope_hz)
    bpm = 60.0 / period_seconds
    return round(bpm, 2), period_seconds


# ---------------------------------------------------------------------------
# Beat grid construction (phase-locked to onsets)
# ---------------------------------------------------------------------------

def build_beats(
    period_seconds: float,
    onsets: list[float],
    duration_seconds: float,
) -> list[float]:
    """Lay a regular grid of ``period_seconds`` phase-aligned to *onsets*.

    The phase is chosen as the circular mean of the onset times modulo the beat
    period, so the grid best fits the detected attacks.  Beats span
    ``[0, duration_seconds]``.  Falls back to a zero-phase grid when there are no
    onsets.
    """
    if period_seconds <= 0 or duration_seconds <= 0:
        return []

    if onsets:
        # Circular mean of (onset mod period) -> a stable phase estimate.
        angles = [(2.0 * np.pi * (t % period_seconds) / period_seconds) for t in onsets]
        mean_angle = float(np.angle(np.mean([np.exp(1j * a) for a in angles])))
        if mean_angle < 0:
            mean_angle += 2.0 * np.pi
        phase = mean_angle / (2.0 * np.pi) * period_seconds
    else:
        phase = 0.0

    # Normalise phase to (-period/2, period/2] so a grid aligned near t=0 keeps
    # its first beat instead of starting a whole period late.
    if phase > period_seconds / 2.0:
        phase -= period_seconds

    beats: list[float] = []
    max_beats = int(duration_seconds / period_seconds) + 4
    k = 0
    while len(beats) <= max_beats:
        t = phase + k * period_seconds
        if t > duration_seconds + 1e-6:
            break
        if t >= -period_seconds / 2.0:
            beats.append(round(max(t, 0.0), 4))
        k += 1
    return beats


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze_beats(
    source: Path,
    sensitivity: float = 0.5,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    envelope_hz: int = DEFAULT_ENVELOPE_HZ,
) -> dict:
    """Detect onsets + tempo + beat grid for a media file.

    Returns ``{bpm_estimate, period_seconds, beats, onsets, duration_seconds,
    envelope_hz, onset_count, beat_count}``.  Pure NumPy on top of FFmpeg decode.
    """
    samples = decode_mono_pcm(Path(source), sample_rate=sample_rate, window_seconds=None)
    duration_seconds = samples.size / float(sample_rate)

    env = energy_envelope(samples, sample_rate=sample_rate, envelope_hz=envelope_hz)
    strength = onset_envelope(env)

    onsets = detect_onset_peaks(strength, envelope_hz, sensitivity)
    bpm, period = estimate_tempo(strength, envelope_hz)
    beats = build_beats(period, onsets, duration_seconds)

    return {
        "bpm_estimate": bpm,
        "period_seconds": round(period, 4),
        "beats": beats,
        "onsets": onsets,
        "duration_seconds": round(duration_seconds, 3),
        "envelope_hz": envelope_hz,
        "sample_rate": sample_rate,
        "sensitivity": float(sensitivity),
        "onset_count": len(onsets),
        "beat_count": len(beats),
    }


# ---------------------------------------------------------------------------
# Beats -> bar markers
# ---------------------------------------------------------------------------

def beats_to_bar_markers(
    beats: list[float],
    every_n: int = 4,
    category: str = "beat",
) -> list[dict]:
    """Convert every ``every_n``-th beat into a bar marker dict.

    Marker dicts use the standard workspace-marker fields (Marker-compatible)
    but carry a free-form ``category`` so callers can tag bars distinctly from
    the transcript-derived enum categories.  ``end_seconds`` mirrors
    ``start_seconds`` (beats are instants).
    """
    step = max(1, int(every_n))
    markers: list[dict] = []
    for bar_index, i in enumerate(range(0, len(beats), step), start=1):
        t = float(beats[i])
        markers.append(
            {
                "category": category,
                "confidence_score": 1.0,
                "source_method": "beat_grid",
                "reason": f"Bar {bar_index} (beat {i + 1})",
                "clip_ref": "",
                "start_seconds": round(t, 4),
                "end_seconds": round(t, 4),
                "suggested_label": f"Bar {bar_index}",
            }
        )
    return markers
