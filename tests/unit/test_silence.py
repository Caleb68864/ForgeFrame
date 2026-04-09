"""Unit tests for the ffmpeg silence detection adapter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence

_MODULE = "workshop_video_brain.edit_mcp.adapters.ffmpeg.silence.subprocess.run"


def _make_result(stderr: str) -> MagicMock:
    mock = MagicMock()
    mock.stderr = stderr
    mock.returncode = 0
    return mock


SILENCE_STDERR_ONE_GAP = """\
  silencedetect @ 0x...] silence_start: 5.3
  silencedetect @ 0x...] silence_end: 8.7 | silence_duration: 3.4
"""

SILENCE_STDERR_TWO_GAPS = """\
  silencedetect @ 0x...] silence_start: 1.0
  silencedetect @ 0x...] silence_end: 3.0 | silence_duration: 2.0
  silencedetect @ 0x...] silence_start: 10.5
  silencedetect @ 0x...] silence_end: 13.0 | silence_duration: 2.5
"""

SILENCE_STDERR_NONE = """\
Input #0, mov,mp4,m4a, from 'clip.mp4':
  Duration: 00:01:30.00
"""

SILENCE_STDERR_UNMATCHED_START = """\
  silencedetect @ 0x...] silence_start: 5.0
  silencedetect @ 0x...] silence_start: 8.0
  silencedetect @ 0x...] silence_end: 10.0 | silence_duration: 2.0
"""


class TestDetectSilence:
    def test_single_silence_gap_parsed(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result(SILENCE_STDERR_ONE_GAP)):
            pairs = detect_silence(fake_file)
        assert len(pairs) == 1
        assert pairs[0][0] == pytest.approx(5.3)
        assert pairs[0][1] == pytest.approx(8.7)

    def test_multiple_silence_gaps_all_captured(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result(SILENCE_STDERR_TWO_GAPS)):
            pairs = detect_silence(fake_file)
        assert len(pairs) == 2
        assert pairs[0] == pytest.approx((1.0, 3.0))
        assert pairs[1] == pytest.approx((10.5, 13.0))

    def test_no_silence_returns_empty_list(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result(SILENCE_STDERR_NONE)):
            pairs = detect_silence(fake_file)
        assert pairs == []

    def test_unmatched_start_skipped(self, tmp_path: Path):
        """If there are more starts than ends, extra starts are skipped (zip behaviour)."""
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result(SILENCE_STDERR_UNMATCHED_START)):
            pairs = detect_silence(fake_file)
        # zip stops at shortest list: 2 starts but only 1 end → 1 pair
        assert len(pairs) == 1

    def test_invalid_ffmpeg_output_no_crash(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result("garbage output")):
            pairs = detect_silence(fake_file)
        assert pairs == []

    def test_empty_stderr_returns_empty(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result("")):
            pairs = detect_silence(fake_file)
        assert pairs == []

    def test_returns_list_of_float_tuples(self, tmp_path: Path):
        fake_file = tmp_path / "clip.mp4"
        fake_file.write_bytes(b"\x00")
        with patch(_MODULE, return_value=_make_result(SILENCE_STDERR_ONE_GAP)):
            pairs = detect_silence(fake_file)
        assert all(isinstance(s, float) and isinstance(e, float) for s, e in pairs)
