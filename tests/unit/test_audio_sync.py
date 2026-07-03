"""Unit tests for the audio-sync pipeline (``edit_mcp/pipelines/audio_sync``).

Covers the pure math (envelope framing, onset, normalized cross-correlation
and its sign convention, parabolic peak refinement), the chromaprint raw
fingerprint parsing/agreement helpers, and MCP-tool registration. No FFmpeg or
files are touched here -- the FFmpeg-gated empirical proof lives in
``tests/integration/test_audio_sync_pipeline.py``.
"""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from workshop_video_brain.edit_mcp.pipelines import audio_sync as A
from workshop_video_brain.server import mcp


# ---------------------------------------------------------------------------
# Envelope math
# ---------------------------------------------------------------------------

def test_energy_envelope_framing_and_rate():
    sr, env_hz = 8000, 100
    # 2 seconds of a constant-amplitude signal -> 200 frames of equal RMS.
    samples = np.full(sr * 2, 0.5, dtype=np.float32)
    env = A.energy_envelope(samples, sr, env_hz)
    assert env.size == 200                      # 2 s * 100 Hz
    assert np.allclose(env, 0.5, atol=1e-6)     # RMS of a constant == the value


def test_energy_envelope_short_signal_returns_single_value():
    env = A.energy_envelope(np.array([0.1, 0.2, 0.3], dtype=np.float32), 8000, 100)
    assert env.size == 1


def test_onset_envelope_is_half_wave_rectified_diff():
    env = np.array([0.0, 1.0, 0.5, 2.0])
    onset = A.onset_envelope(env)
    # diff (prepend first) = [0, 1, -0.5, 1.5] -> negatives clipped to 0.
    assert np.allclose(onset, [0.0, 1.0, 0.0, 1.5])
    assert np.all(onset >= 0.0)


# ---------------------------------------------------------------------------
# Cross-correlation: value, sign convention, sub-sample refinement
# ---------------------------------------------------------------------------

def test_cross_correlate_recovers_positive_delay():
    # target is ref delayed by 20 frames => offset (delay of target) = +20.
    rng = np.random.default_rng(1)
    ref = rng.standard_normal(500)
    ref[100:130] += 5.0                      # a distinctive burst
    delay = 20
    target = np.concatenate([np.zeros(delay), ref])[: ref.size]
    lag, conf = A.cross_correlate_lag(ref, target)
    assert abs(lag - delay) < 0.5            # sub-frame accurate
    assert conf > 0.8


def test_cross_correlate_sign_is_symmetric():
    rng = np.random.default_rng(2)
    ref = rng.standard_normal(400)
    ref[50:70] += 4.0
    target = np.concatenate([np.zeros(15), ref])[: ref.size]
    lag_fwd, _ = A.cross_correlate_lag(ref, target)
    lag_rev, _ = A.cross_correlate_lag(target, ref)
    # Swapping arguments flips the sign of the recovered lag.
    assert abs(lag_fwd + lag_rev) < 1.0
    assert lag_fwd > 0 > lag_rev


def test_cross_correlate_flat_series_is_zero_confidence():
    lag, conf = A.cross_correlate_lag(np.zeros(100), np.zeros(100))
    assert lag == 0.0 and conf == 0.0


def test_parabolic_refine_interpolates_between_frames():
    # Symmetric triangle peaks exactly on the sample -> zero fractional shift.
    corr = np.array([0.0, 1.0, 2.0, 1.0, 0.0])
    assert abs(A._parabolic_refine(corr, 2)) < 1e-9
    # Skewed peak -> fractional shift toward the higher shoulder.
    corr2 = np.array([0.0, 1.0, 2.0, 1.5, 0.0])
    assert A._parabolic_refine(corr2, 2) > 0.0
    # Guard rails at the array edges.
    assert A._parabolic_refine(corr, 0) == 0.0
    assert A._parabolic_refine(corr, corr.size - 1) == 0.0


def test_normalize_zero_mean_unit_norm():
    out = A._normalize(np.array([1.0, 2.0, 3.0, 4.0]))
    assert abs(out.mean()) < 1e-12
    assert abs(np.linalg.norm(out) - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# Chromaprint helpers (no ffmpeg needed -- pure parsing / bit math)
# ---------------------------------------------------------------------------

def test_fingerprint_bit_agreement_recovers_item_lag():
    rng = np.random.default_rng(3)
    fp = rng.integers(0, 2**32, size=200, dtype=np.uint64).astype(np.uint32)
    lag = 12
    fp_b = np.concatenate([rng.integers(0, 2**32, size=lag, dtype=np.uint64).astype(np.uint32), fp])
    lag_items, conf = A._fingerprint_bit_agreement(fp, fp_b)
    assert lag_items == lag                  # b is a delayed by `lag` items
    assert conf > 0.9                        # identical overlap => near-perfect


def test_fingerprint_bit_agreement_empty_is_zero():
    lag, conf = A._fingerprint_bit_agreement(np.array([], dtype=np.uint32),
                                             np.array([1], dtype=np.uint32))
    assert lag == 0.0 and conf == 0.0


def test_chromaprint_item_hz_constant():
    # ~8.08 items/sec for the default chromaprint algorithm.
    assert 8.0 < A._CHROMAPRINT_ITEM_HZ < 8.2


# ---------------------------------------------------------------------------
# Orchestrator guard rails (no ffmpeg invocation on these paths)
# ---------------------------------------------------------------------------

def test_sync_by_audio_missing_file_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "ffmpeg_available", lambda: True)
    res = A.sync_by_audio(tmp_path / "nope_a.wav", tmp_path / "nope_b.wav")
    assert res["success"] is False
    assert "not found" in res["error"].lower()


def test_sync_by_audio_unknown_method(tmp_path, monkeypatch):
    a = tmp_path / "a.wav"; a.write_bytes(b"x")
    b = tmp_path / "b.wav"; b.write_bytes(b"x")
    monkeypatch.setattr(A, "ffmpeg_available", lambda: True)
    res = A.sync_by_audio(a, b, method="bogus")
    assert res["success"] is False and "bogus" in res["error"]


def test_sync_by_audio_chromaprint_unavailable_is_actionable(tmp_path, monkeypatch):
    a = tmp_path / "a.wav"; a.write_bytes(b"x")
    b = tmp_path / "b.wav"; b.write_bytes(b"x")
    monkeypatch.setattr(A, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(A, "chromaprint_available", lambda: False)
    res = A.sync_by_audio(a, b, method="chromaprint")
    assert res["success"] is False
    assert "chromaprint" in res["error"].lower()
    assert "correlate" in res["error"].lower()   # points at the fallback


def test_sync_result_as_dict_shape():
    r = A.SyncResult(offset_seconds=3.7001, confidence=0.912345, method="correlate",
                     lag_units=370.01, unit_hz=100.0, samples_a=1200, samples_b=1570)
    d = r.as_dict()
    assert d["offset_seconds"] == 3.7001
    assert d["confidence"] == 0.9123
    assert d["method"] == "correlate"
    assert d["series_len_a"] == 1200 and d["series_len_b"] == 1570


# ---------------------------------------------------------------------------
# MCP registration (the `.fn`-unwrap / list_tools pattern)
# ---------------------------------------------------------------------------

def _registered_tool_names() -> set[str]:
    getter = getattr(mcp, "get_tools", None) or getattr(mcp, "list_tools", None)
    result = asyncio.run(getter())
    if isinstance(result, dict):
        return set(result.keys())
    return {getattr(t, "name", getattr(t, "key", str(t))) for t in result}


def test_media_sync_by_audio_is_registered():
    # Importing the bundle package auto-discovers and registers the tool.
    import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401
    assert "media_sync_by_audio" in _registered_tool_names()


def test_media_sync_by_audio_validates_sources(tmp_path):
    from workshop_video_brain.edit_mcp.server.bundles.audio_sync import (
        media_sync_by_audio,
    )
    fn = getattr(media_sync_by_audio, "fn", media_sync_by_audio)
    res = fn(str(tmp_path), source_a="", source_b="")
    assert res["status"] == "error"
    assert "required" in res["message"].lower()
