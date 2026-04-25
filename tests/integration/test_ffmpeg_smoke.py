"""End-to-end smoke tests for the ffmpeg adapters.

Real ffmpeg/ffprobe subprocess execution -- not mocks.  Verifies that
each adapter produces correct output, respects the per-call timeouts we
added during the v25 work, and handles common edge cases without
hanging.

Skipped automatically if ffmpeg/ffprobe is not on PATH.

Test budget: each test should complete in < 30 seconds; total file
runs in under 2 minutes on a workstation.

Skipped (intentionally) for runtime reasons:
* whisper_engine.transcribe -- needs the Whisper model download
* render_executor / render pipeline -- needs MLT melt installed
* audio_enhance_all -- workspace-wide, large
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest


import os

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
SILENCE_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_audio_with_silence.mp4"
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")

# Common Windows install locations for ffmpeg + this user's known custom path.
# Tests prepend the first directory containing ffmpeg.exe to PATH for the
# session so the production adapters' bare ``subprocess.run(["ffmpeg", ...])``
# calls succeed without requiring the user to add ffmpeg to their system PATH.
_FFMPEG_DIR_CANDIDATES = [
    Path("C:/Users/CalebBennett/Music/Get Music"),
    Path("C:/ffmpeg/bin"),
    Path("C:/Program Files/ffmpeg/bin"),
]


def _ensure_ffmpeg_on_path() -> bool:
    """Return True if ffmpeg+ffprobe are reachable via ``shutil.which``,
    after optionally prepending a known directory to PATH."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return True
    for d in _FFMPEG_DIR_CANDIDATES:
        if (d / "ffmpeg.exe").exists() and (d / "ffprobe.exe").exists():
            os.environ["PATH"] = f"{d}{os.pathsep}{os.environ.get('PATH', '')}"
            if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                return True
    return False


_FFMPEG_OK = _ensure_ffmpeg_on_path()

pytestmark = pytest.mark.skipif(
    not _FFMPEG_OK,
    reason="ffmpeg/ffprobe not discoverable",
)


# ---------------------------------------------------------------------------
# probe.scan_directory
# ---------------------------------------------------------------------------


def test_probe_scan_directory_lists_generated_clips():
    """``scan_directory`` should find both generated test fixtures and
    return MediaAsset records with width/height/duration populated."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory

    fixtures_dir = REPO_ROOT / "tests" / "fixtures" / "media_generated"
    if not fixtures_dir.exists():
        pytest.skip("media_generated fixture dir missing")

    started = time.monotonic()
    assets = scan_directory(fixtures_dir)
    elapsed = time.monotonic() - started

    # ffprobe per file is sub-second; whole pass should be <5s.
    assert elapsed < 10.0, f"scan_directory took {elapsed:.1f}s"
    # At least the two generated clips should be present.
    by_name = {Path(a.path).name: a for a in assets}
    assert "test_clip_1080p2997_5s.mp4" in by_name
    asset = by_name["test_clip_1080p2997_5s.mp4"]
    assert asset.width == 1920
    assert asset.height == 1080
    assert asset.duration > 4.0  # 5-second clip
    assert asset.media_type == "video"


def test_probe_scan_directory_handles_missing_dir(tmp_path):
    """Scanning a directory with no media should return an empty list,
    not raise."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory

    empty = tmp_path / "empty"
    empty.mkdir()
    assets = scan_directory(empty)
    assert assets == []


# ---------------------------------------------------------------------------
# silence.detect_silence
# ---------------------------------------------------------------------------


def test_silence_detect_finds_known_gap():
    """``test_audio_with_silence.mp4`` is built as 1.5s tone / 2s silence /
    1.5s tone.  detect_silence should return a single gap covering
    roughly 1.5s..3.5s."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence

    if not SILENCE_CLIP.exists():
        pytest.skip(f"Silence clip missing: {SILENCE_CLIP}")

    gaps = detect_silence(SILENCE_CLIP, threshold_db=-30.0, min_duration=0.5)
    assert len(gaps) >= 1, f"expected at least one silence gap, got {gaps}"
    start, end = gaps[0]
    # The silence is 1.5s..3.5s in the source.  Allow ±0.3s slop for
    # encoder padding and silencedetect's threshold sensitivity.
    assert 1.0 <= start <= 1.8, f"silence_start {start:.2f}s out of range"
    assert 3.2 <= end <= 4.0, f"silence_end {end:.2f}s out of range"


def test_silence_detect_finds_no_gaps_in_continuous_tone():
    """The 1kHz tone clip has no silence; detect_silence should return []."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence

    if not GENERATED_CLIP.exists():
        pytest.skip(f"Generated clip missing: {GENERATED_CLIP}")

    gaps = detect_silence(GENERATED_CLIP, threshold_db=-30.0, min_duration=0.5)
    assert gaps == [], f"expected no silence in continuous tone, got {gaps}"


# ---------------------------------------------------------------------------
# proxy.generate_proxy
# ---------------------------------------------------------------------------


def test_proxy_needs_proxy_for_uhd():
    """``needs_proxy`` should return True for a 3840×2160 source."""
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import needs_proxy

    asset = MediaAsset(
        path="/tmp/uhd.mp4",
        media_type="video",
        width=3840,
        height=2160,
        duration=5.0,
        bitrate=20_000_000,
        video_codec="h264",
    )
    assert needs_proxy(asset) is True


def test_proxy_does_not_need_proxy_for_hd():
    """1080p H.264 should not trigger proxy generation."""
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import needs_proxy

    asset = MediaAsset(
        path="/tmp/hd.mp4",
        media_type="video",
        width=1920,
        height=1080,
        duration=5.0,
        bitrate=8_000_000,
        video_codec="h264",
    )
    assert needs_proxy(asset) is False


def test_proxy_generate_real_uhd_clip(tmp_path):
    """End-to-end: run generate_proxy on a real UHD source and verify the
    output is 720p-class.  Limited to a SHORT UHD clip (~9 seconds) so
    the test stays under 30 seconds."""
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import generate_proxy

    src = USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4"
    if not src.exists():
        pytest.skip("UHD source missing")

    asset = MediaAsset(
        path=str(src),
        media_type="video",
        width=3840,
        height=2160,
        duration=8.5,
        bitrate=20_000_000,
        video_codec="h264",
    )
    out_dir = tmp_path / "proxies"
    started = time.monotonic()
    proxy_path = generate_proxy(asset, out_dir, timeout=60)
    elapsed = time.monotonic() - started

    assert proxy_path.exists()
    # Should complete well under the 60s timeout for a ~9s clip.
    assert elapsed < 60, f"proxy took {elapsed:.1f}s"

    # Probe the output and verify it's 720p-class.
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "default=nw=1:nk=1",
            str(proxy_path),
        ],
        capture_output=True, text=True, check=True, timeout=10,
    )
    lines = result.stdout.strip().split()
    width, height = int(lines[0]), int(lines[1])
    assert height == 720, f"expected 720p proxy, got {width}x{height}"
    # Aspect ratio preserved (1280x720 from 3840x2160).
    assert width in {1280, 1281}, f"expected ~1280px width, got {width}"


def test_proxy_generate_skips_when_up_to_date(tmp_path):
    """Calling generate_proxy twice should be idempotent: the second
    call returns the existing proxy without re-encoding."""
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import generate_proxy

    src = USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4"
    if not src.exists():
        pytest.skip("UHD source missing")

    asset = MediaAsset(
        path=str(src),
        media_type="video",
        width=3840, height=2160, duration=8.5,
        bitrate=20_000_000, video_codec="h264",
    )
    out_dir = tmp_path / "proxies"
    p1 = generate_proxy(asset, out_dir, timeout=60)
    mtime1 = p1.stat().st_mtime
    started = time.monotonic()
    p2 = generate_proxy(asset, out_dir, timeout=60)
    elapsed = time.monotonic() - started

    assert p1 == p2
    assert p2.stat().st_mtime == mtime1, "second call should not re-encode"
    assert elapsed < 1.0, f"second call took {elapsed:.1f}s (should be ~instant)"


# ---------------------------------------------------------------------------
# runner.run_ffmpeg (generic FFmpegResult interface)
# ---------------------------------------------------------------------------


def test_run_ffmpeg_normalize_audio(tmp_path):
    """Run a generic ffmpeg job through the FFmpegResult runner: normalize
    a 5-second audio clip's loudness."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg

    if not GENERATED_CLIP.exists():
        pytest.skip("Generated clip missing")

    out_path = tmp_path / "normalized.mp4"
    result = run_ffmpeg(
        args=[
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
        ],
        input_path=GENERATED_CLIP,
        output_path=out_path,
    )
    assert result.success, result.stderr[-500:]
    assert out_path.exists()
    assert out_path.stat().st_size > 1000, "output unexpectedly small"


def test_run_ffmpeg_dry_run_returns_command_without_executing(tmp_path):
    """``dry_run=True`` should return the FFmpegResult with the planned
    command and no output file written."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg

    out = tmp_path / "should_not_exist.mp4"
    result = run_ffmpeg(
        args=["-c:v", "copy"],
        input_path=tmp_path / "fake.mp4",
        output_path=out,
        dry_run=True,
    )
    assert result.success is True
    assert "ffmpeg" in result.command[0]
    assert "-i" in result.command
    assert not out.exists()


# ---------------------------------------------------------------------------
# Whisper extract_audio (just the audio extraction step, not transcription)
# ---------------------------------------------------------------------------


def test_whisper_extract_audio(tmp_path):
    """``whisper_engine.extract_audio`` runs ffmpeg to pull a 16-kHz PCM
    WAV from a video.  No Whisper model needed for this step.  The
    extractor preserves the source's channel count (no ``-ac 1`` flag),
    so a stereo source yields a stereo WAV."""
    from workshop_video_brain.edit_mcp.adapters.stt.whisper_engine import extract_audio

    if not GENERATED_CLIP.exists():
        pytest.skip("Generated clip missing")

    out_wav = tmp_path / "extracted.wav"
    extract_audio(GENERATED_CLIP, out_wav)
    assert out_wav.exists()
    assert out_wav.stat().st_size > 1000

    # Verify sample rate is downsampled to 16kHz.  Channels match source.
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "default=nw=1:nk=1",
            str(out_wav),
        ],
        capture_output=True, text=True, check=True, timeout=10,
    )
    sr_str, ch_str = result.stdout.strip().split()
    assert int(sr_str) == 16000
    assert int(ch_str) in (1, 2)  # source channel count preserved


# ---------------------------------------------------------------------------
# Timeout enforcement (smoke test that the timeout we added really fires)
# ---------------------------------------------------------------------------


def test_proxy_timeout_fires_on_unrealistic_budget(tmp_path):
    """Set an absurdly short timeout and confirm ``generate_proxy`` raises
    ``subprocess.TimeoutExpired`` rather than blocking.  This guards
    against timeouts being silently dropped during refactors."""
    from workshop_video_brain.core.models import MediaAsset
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import generate_proxy

    src = USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4"  # ~32s UHD
    if not src.exists():
        pytest.skip("Long UHD source missing")

    asset = MediaAsset(
        path=str(src),
        media_type="video",
        width=3840, height=2160, duration=32.0,
        bitrate=17_000_000, video_codec="h264",
    )
    out_dir = tmp_path / "timeout_proxies"
    with pytest.raises(subprocess.TimeoutExpired):
        # 1 second is well below the ~10-30s the proxy encode would need.
        generate_proxy(asset, out_dir, timeout=1)
    # Partial output should be cleaned up.
    leftovers = list(out_dir.glob("*.mp4")) if out_dir.exists() else []
    assert leftovers == [], f"timeout left partial files: {leftovers}"
