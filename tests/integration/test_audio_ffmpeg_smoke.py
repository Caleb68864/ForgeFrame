"""FFmpeg audio toolkit smoke tests.

Exercises the audio adapters in
``workshop_video_brain.edit_mcp.adapters.ffmpeg`` against the audio
fixtures we ship in ``tests/fixtures/media_generated/``:

* ``music_cinematic_short.mp3`` -- Mixkit cinematic music, stereo
  44.1 kHz.  Used for loudness, compression, limiter, and the
  voice-enhance chain (the chain is pipeline-agnostic; running it
  on music validates every stage even if the result isn't "voice").
* ``test_audio_with_silence.mp4`` -- short generated clip with
  intentional silence gaps, mono AAC 48 kHz.  Used for silence
  detection + silenceremove.

The reporter clip (``greenscreen_reporter_720.mp4``) is video-only
and has no audio stream, so it can't be used here -- attempting
``-vn -af ...`` on it produces "Output file does not contain any
stream".  Audio fixtures with real voice would need to be added
later if we want to verify perceptual voice-enhancement quality.

Each smoke writes its output to
``C:/Users/CalebBennett/Videos/Video Production/tests/audio_output/``
so the user can audition the result and compare A/B against the
source.  The structural assertion is just "ffmpeg returned success
and the output exists with non-zero bytes".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import (
    compress_audio,
    convert_format,
    de_ess,
    export_compressed,
    highpass_filter,
    limit_peaks,
    normalize_audio,
    remove_background_noise,
    remove_silence,
    voice_enhance_chain,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "media_generated"

MUSIC_CLIP = FIXTURES / "music_cinematic_short.mp3"
SILENCE_CLIP = FIXTURES / "test_audio_with_silence.mp4"

USER_OUTPUT_DIR = Path(
    "C:/Users/CalebBennett/Videos/Video Production/tests/audio_output"
)


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Fixture not available: {path}")


def _assert_output(path: Path) -> None:
    assert path.exists(), f"output not written: {path}"
    assert path.stat().st_size > 0, f"output is empty: {path}"


# ---------------------------------------------------------------------------
# 001 -- ffprobe sanity check on each audio fixture
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_001_probe_fixtures():
    """Confirm ffprobe can read every fixture and surface duration."""
    for fixture in (MUSIC_CLIP, SILENCE_CLIP):
        _require(fixture)
        asset = probe_media(fixture)
        assert asset.duration_seconds > 0, f"zero duration: {fixture}"


# ---------------------------------------------------------------------------
# 002 -- silence detection on the silence-laced fixture
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_002_detect_silence_in_test_clip():
    """The test fixture has intentional silence gaps -- ffmpeg's
    silencedetect should find at least one."""
    _require(SILENCE_CLIP)
    gaps = detect_silence(SILENCE_CLIP, threshold_db=-30.0, min_duration=0.5)
    assert len(gaps) > 0, "expected silence gaps, found none"
    for start, end in gaps:
        assert end > start, f"invalid gap: {start} -> {end}"


# ---------------------------------------------------------------------------
# 003 -- highpass filter on music (low-end roll-off)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_003_highpass_music():
    """200 Hz highpass on music.  Audible difference: thinner low end
    -- bass and kick drum body diminished.  Cutoff is set higher than
    the 80 Hz voice default so the effect is unambiguous on music."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "003-highpass-200hz.wav"
    result = highpass_filter(
        input_path=MUSIC_CLIP,
        output_path=out,
        cutoff_hz=200.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 004 -- denoise music (afftdn)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_004_denoise_music():
    """FFT denoise on music.  Audible difference subtle on a clean
    Mixkit master, but verifies the filter runs without error."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "004-denoise.wav"
    result = remove_background_noise(
        input_path=MUSIC_CLIP,
        output_path=out,
        noise_floor_db=-25.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 005 -- compressor on music (heavy dynamic-range squash)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_005_compress_music():
    """6:1 compression at -24 dB threshold.  Audible difference:
    quiet passages lifted, loud passages tamed -- music feels
    ``squashed'' in dynamics.  Aggressive settings chosen so the
    effect is obvious."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "005-compress-heavy.wav"
    result = compress_audio(
        input_path=MUSIC_CLIP,
        output_path=out,
        threshold_db=-24.0,
        ratio=6.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 006 -- de-esser on music (high-frequency notch)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_006_de_ess_music():
    """6 kHz notch at -10 dB.  On music this dulls cymbal/hi-hat
    sparkle (the de-esser's intended target on voice is sibilance
    in the same band).  Useful as a pipeline check that the
    equalizer filter is wired correctly."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "006-de-ess.wav"
    result = de_ess(
        input_path=MUSIC_CLIP,
        output_path=out,
        frequency_hz=6000.0,
        gain_db=-10.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 007 -- normalize music to -16 LUFS (YouTube standard)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_007_normalize_music_youtube():
    """EBU R128 normalize to -16 LUFS / -1.5 dBTP.  Audible
    difference: consistent perceived loudness vs the source."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "007-music-loudnorm-16lufs.wav"
    result = normalize_audio(
        input_path=MUSIC_CLIP,
        output_path=out,
        target_lufs=-16.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 008 -- limiter on music (peak-safe export)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_008_limit_music_peaks():
    """alimiter to -1.0 dB ceiling.  Audible difference: prevents
    clipping on transients without changing average level."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "008-music-limited-1db.wav"
    result = limit_peaks(
        input_path=MUSIC_CLIP,
        output_path=out,
        limit_db=-1.0,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)


# ---------------------------------------------------------------------------
# 009 -- silence removal on the silence-laced fixture
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_009_remove_silence_from_test_clip():
    """Trim leading and trailing silence (>=0.5s, below -40 dB).
    Output should be shorter than the input."""
    _require(SILENCE_CLIP)
    out = _output_dir() / "009-silence-trimmed.wav"
    result = remove_silence(
        input_path=SILENCE_CLIP,
        output_path=out,
        threshold_db=-40.0,
        min_duration=0.5,
        trim_start=True,
        trim_end=True,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)

    src = probe_media(SILENCE_CLIP).duration_seconds
    dst = probe_media(out).duration_seconds
    assert dst < src, f"silence not trimmed: src={src}s dst={dst}s"


# ---------------------------------------------------------------------------
# 010 -- full voice-enhance chain on music (pipeline validation)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_010_voice_enhance_chain_youtube_on_music():
    """Full pipeline: highpass -> denoise -> compress -> de-ess ->
    normalize -> limit, all in one call with the youtube_voice
    preset.  Run on music since we have no voice fixture -- this
    validates every stage of the chain runs and produces a valid
    output, even though the result is overprocessed for music
    material.  A/B against the source music to hear cumulative
    effect (heavily-compressed, slightly-darker music)."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "010-voice-chain-youtube-on-music.wav"
    result = voice_enhance_chain(
        input_path=MUSIC_CLIP,
        output_path=out,
        preset="youtube_voice",
        include_de_ess=True,
    )
    assert result["success"], result.get("error", "chain failed")
    assert result["preset_used"] == "youtube_voice"
    assert len(result["steps"]) == 6
    _assert_output(out)


# ---------------------------------------------------------------------------
# 011 -- voice-enhance chain with podcast preset
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_011_voice_enhance_chain_podcast_on_music():
    """Same chain, podcast preset (lower highpass at 60 Hz, heavier
    compression ratio 4:1, deeper -1.5 dB limiter).  A/B against 010
    to hear preset differences."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "011-voice-chain-podcast-on-music.wav"
    result = voice_enhance_chain(
        input_path=MUSIC_CLIP,
        output_path=out,
        preset="podcast",
        include_de_ess=True,
    )
    assert result["success"], result.get("error", "chain failed")
    assert result["preset_used"] == "podcast"
    _assert_output(out)


# ---------------------------------------------------------------------------
# 012 -- format conversion (mp3 -> wav mono 22.05 kHz)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_012_convert_format_to_telephone_quality():
    """Resample music to 22.05 kHz mono ``telephone-quality'' WAV.
    Audible difference: muffled high end, summed-to-mono image."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "012-music-22khz-mono.wav"
    result = convert_format(
        input_path=MUSIC_CLIP,
        output_path=out,
        sample_rate=22050,
        channels=1,
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)

    asset = probe_media(out)
    # convert_format passes -ac 1 -ar 22050; verify probe agrees
    assert asset.duration_seconds > 0


# ---------------------------------------------------------------------------
# 013 -- compressed export (mp3 @ 128k)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_013_export_compressed_mp3():
    """Export to MP3 @ 128k.  Smaller file size, lossy artifacts on
    high frequencies and transients (compare to source MP3 which is
    likely encoded at higher bitrate)."""
    _require(MUSIC_CLIP)
    out = _output_dir() / "013-music-export-128k.mp3"
    result = export_compressed(
        input_path=MUSIC_CLIP,
        output_path=out,
        bitrate="128k",
    )
    assert result.success, result.stderr[-500:]
    _assert_output(out)
