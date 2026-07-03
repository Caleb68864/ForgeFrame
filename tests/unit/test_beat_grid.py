"""Unit tests for the beat-grid pipeline (pure NumPy; no ffmpeg)."""
from __future__ import annotations

import numpy as np

from workshop_video_brain.edit_mcp.pipelines import beat_grid as bg


def _click_strength(bpm: float, seconds: float, hz: int) -> np.ndarray:
    """Synthesise an onset-strength envelope with impulses at a fixed tempo."""
    period = 60.0 / bpm
    strength = np.zeros(int(seconds * hz))
    n_beats = int(seconds / period)
    for k in range(n_beats):
        idx = int(round(k * period * hz))
        if idx < strength.size:
            strength[idx] = 1.0
    return strength


# ---------------------------------------------------------------------------
# Onset peak-picking
# ---------------------------------------------------------------------------

def test_detect_onset_peaks_finds_impulses():
    hz = 200
    strength = _click_strength(120, 6.0, hz)  # impulses every 0.5s
    onsets = bg.detect_onset_peaks(strength, hz, sensitivity=0.5)
    # Every detected onset lands within 10 ms of a 0.5 s multiple.
    for o in onsets:
        nearest = round(o / 0.5) * 0.5
        assert abs(o - nearest) <= 0.01, (o, nearest)
    assert len(onsets) >= 10


def test_detect_onset_peaks_empty_and_flat():
    assert bg.detect_onset_peaks(np.array([]), 200, 0.5) == []
    assert bg.detect_onset_peaks(np.zeros(100), 200, 0.5) == []


def test_detect_onset_peaks_respects_refractory_window():
    hz = 200
    strength = np.zeros(400)
    # Two very close spikes (10 ms apart) should collapse to one onset.
    strength[100] = 1.0
    strength[102] = 0.9
    onsets = bg.detect_onset_peaks(strength, hz, sensitivity=0.5)
    assert len(onsets) == 1


# ---------------------------------------------------------------------------
# Tempo via autocorrelation
# ---------------------------------------------------------------------------

def test_estimate_tempo_recovers_120_bpm():
    hz = 200
    strength = _click_strength(120, 8.0, hz)
    bpm, period = bg.estimate_tempo(strength, hz)
    assert abs(bpm - 120.0) <= 2.0
    assert abs(period - 0.5) <= 0.01


def test_estimate_tempo_recovers_90_bpm():
    hz = 200
    strength = _click_strength(90, 10.0, hz)
    bpm, _ = bg.estimate_tempo(strength, hz)
    assert abs(bpm - 90.0) <= 2.0


def test_estimate_tempo_flat_signal_returns_zero():
    bpm, period = bg.estimate_tempo(np.zeros(500), 200)
    assert bpm == 0.0 and period == 0.0


# ---------------------------------------------------------------------------
# Beat grid construction
# ---------------------------------------------------------------------------

def test_build_beats_grid_aligned_to_onsets():
    onsets = [round(k * 0.5, 4) for k in range(1, 12)]
    beats = bg.build_beats(0.5, onsets, 6.0)
    assert beats[0] == 0.0
    assert abs(beats[-1] - 6.0) <= 0.5
    # Consecutive spacing == period.
    diffs = [round(b2 - b1, 4) for b1, b2 in zip(beats, beats[1:])]
    assert all(abs(d - 0.5) < 1e-6 for d in diffs)


def test_build_beats_empty_when_no_period():
    assert bg.build_beats(0.0, [1.0], 5.0) == []
    assert bg.build_beats(0.5, [], 0.0) == []


def test_build_beats_zero_phase_when_no_onsets():
    beats = bg.build_beats(0.5, [], 2.0)
    assert beats[0] == 0.0


# ---------------------------------------------------------------------------
# Beats -> bar markers
# ---------------------------------------------------------------------------

def test_beats_to_bar_markers_every_fourth():
    beats = [round(k * 0.5, 4) for k in range(16)]  # 0..7.5
    markers = bg.beats_to_bar_markers(beats, every_n=4, category="beat")
    # Bars at beats 0, 4, 8, 12 -> 0.0, 2.0, 4.0, 6.0
    assert [m["start_seconds"] for m in markers] == [0.0, 2.0, 4.0, 6.0]
    assert all(m["category"] == "beat" for m in markers)
    assert markers[0]["suggested_label"] == "Bar 1"
    assert markers[0]["end_seconds"] == markers[0]["start_seconds"]


def test_beats_to_bar_markers_custom_category_and_step():
    beats = [round(k * 0.5, 4) for k in range(8)]
    markers = bg.beats_to_bar_markers(beats, every_n=2, category="downbeat")
    assert [m["start_seconds"] for m in markers] == [0.0, 1.0, 2.0, 3.0]
    assert all(m["category"] == "downbeat" for m in markers)
