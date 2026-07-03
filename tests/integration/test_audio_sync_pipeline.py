"""Empirical proof for the audio-sync pipeline.

Synthesises two WAV files with FFmpeg that captured the *same* pattern of tone
bursts, where file B is file A delayed by a known offset (3.7 s) and carries a
*different* noise bed. Runs both through ``sync_by_audio`` / the
``media_sync_by_audio`` MCP tool and asserts the recovered offset is within
+/-50 ms of the truth, with the correct sign.

Lives in ``tests/integration/`` (not ``external/``): it only uses the local
FFmpeg install -- no network, no third-party service. Skipped automatically
when ffmpeg is not on PATH.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.audio_sync import sync_by_audio

ffmpeg_available = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg not available on PATH"
)

KNOWN_OFFSET = 3.7          # seconds B lags behind A
TOLERANCE = 0.05            # +/-50 ms
SR = 44100


def _synth_event_wav(
    path: Path,
    lead_silence: float,
    noise_seed: int,
    total_seconds: float = 18.0,
) -> None:
    """Render a WAV: ``lead_silence`` of quiet, then a fixed pattern of tone
    bursts, all under a distinct low-level noise bed (``noise_seed``).

    The burst *pattern* is identical across files; only the lead-in and the
    noise differ -- exactly the multicam situation (same event, two recorders
    that started at different moments with different room noise).
    """
    # Distinctive, non-periodic burst schedule (start_s, freq_hz).
    bursts = [(1.0, 440), (2.6, 880), (4.9, 330), (7.1, 660), (9.8, 550)]
    # Sum of gated sines, each shifted by the lead-in silence.
    tone_terms = []
    for start, freq in bursts:
        t0 = start + lead_silence
        gate = f"between(t,{t0:.3f},{t0 + 0.4:.3f})"
        tone_terms.append(f"0.6*sin(2*PI*{freq}*t)*({gate})")
    tone_expr = "+".join(tone_terms)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        # Track 1: the shared burst pattern (aevalsrc).
        "-f", "lavfi", "-i",
        f"aevalsrc='{tone_expr}':s={SR}:d={total_seconds}",
        # Track 2: a per-file random noise bed (different seed => different noise).
        "-f", "lavfi", "-i",
        f"anoisesrc=color=white:seed={noise_seed}:amplitude=0.05:"
        f"sample_rate={SR}:duration={total_seconds}",
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest[out]",
        "-map", "[out]",
        "-ac", "1", "-ar", str(SR),
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture()
def synced_pair(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    a = raw / "camA.wav"
    b = raw / "camB.wav"
    # A: event starts at 0.0 lead-in; B: same event but 3.7 s later, other noise.
    _synth_event_wav(a, lead_silence=0.0, noise_seed=11)
    _synth_event_wav(b, lead_silence=KNOWN_OFFSET, noise_seed=99)
    assert a.stat().st_size > 0 and b.stat().st_size > 0
    return a, b


class TestAudioSyncEmpirical:
    def test_recovers_known_offset_within_50ms(self, synced_pair):
        a, b = synced_pair
        res = sync_by_audio(a, b, method="correlate", window_seconds=120)
        assert res["success"] is True, res
        recovered = res["offset_seconds"]
        # B lags A by +3.7 s (event appears later into B).
        assert recovered == pytest.approx(KNOWN_OFFSET, abs=TOLERANCE), (
            f"expected {KNOWN_OFFSET}s, recovered {recovered}s"
        )
        assert res["confidence"] > 0.3
        assert res["method"] == "correlate"

    def test_offset_sign_flips_when_sources_swapped(self, synced_pair):
        a, b = synced_pair
        fwd = sync_by_audio(a, b, window_seconds=120)["offset_seconds"]
        rev = sync_by_audio(b, a, window_seconds=120)["offset_seconds"]
        assert fwd == pytest.approx(KNOWN_OFFSET, abs=TOLERANCE)
        assert rev == pytest.approx(-KNOWN_OFFSET, abs=TOLERANCE)

    def test_energy_method_also_recovers_offset(self, synced_pair):
        a, b = synced_pair
        # Same estimate without the onset transform (raw energy envelope).
        res = sync_by_audio(a, b, window_seconds=120, use_onset=False)
        assert res["success"] is True
        assert res["offset_seconds"] == pytest.approx(KNOWN_OFFSET, abs=TOLERANCE)

    def test_window_seconds_bounds_analysis(self, synced_pair):
        a, b = synced_pair
        # A short window still spans the first bursts; offset must survive.
        res = sync_by_audio(a, b, window_seconds=12)
        assert res["success"] is True
        assert res["offset_seconds"] == pytest.approx(KNOWN_OFFSET, abs=TOLERANCE)
        assert res["window_seconds"] == 12

    def test_mcp_tool_end_to_end(self, synced_pair, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.audio_sync import (
            media_sync_by_audio,
        )
        fn = getattr(media_sync_by_audio, "fn", media_sync_by_audio)
        res = fn(
            str(tmp_path),
            source_a="media/raw/camA.wav",
            source_b="media/raw/camB.wav",
            method="correlate",
            window_seconds=120,
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["offset_seconds"] == pytest.approx(KNOWN_OFFSET, abs=TOLERANCE)
        assert "confidence" in data


class TestChromaprintGate:
    def test_chromaprint_unavailable_returns_actionable_error(self, synced_pair):
        from workshop_video_brain.edit_mcp.pipelines.audio_sync import (
            chromaprint_available,
        )

        a, b = synced_pair
        res = sync_by_audio(a, b, method="chromaprint", window_seconds=60)
        if chromaprint_available():
            # Build has the muxer: it should actually recover the offset.
            assert res["success"] is True
            assert res["offset_seconds"] == pytest.approx(KNOWN_OFFSET, abs=0.3)
        else:
            assert res["success"] is False
            assert "chromaprint" in res["error"].lower()
            assert "correlate" in res["error"].lower()
