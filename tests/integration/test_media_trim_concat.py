"""media_trim / media_concat on real files (prompt 30)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, make_test_clip, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.server.bundles.media_concat import media_concat
from workshop_video_brain.edit_mcp.server.bundles.media_trim import media_trim

pytestmark = requires_ffmpeg_ffprobe
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("media_trim", "media_concat")


def test_accurate_trim(tmp_path):
    data = _ok(call_tool(media_trim, str(FIX / "test_clip_1080p2997_5s.mp4"), 1.0, end_seconds=3.0,
                         output_dir=str(tmp_path)))
    assert data["duration_seconds"] == pytest.approx(2.0, abs=0.05)
    assert (data["width"], data["height"], data["has_audio"]) == (1920, 1080, True)


def test_copy_trim_snaps_to_keyframes(tmp_path):
    clip = make_test_clip(tmp_path / "src.mp4", duration=5.0, with_audio=True)
    gop = tmp_path / "gop5.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-c:v", "libx264", "-g", "5", "-keyint_min", "5",
                    "-sc_threshold", "0", "-c:a", "aac", str(gop)], check=True, capture_output=True, timeout=120)
    data = _ok(call_tool(media_trim, str(gop), 1.0, duration_seconds=2.0, mode="copy", output_dir=str(tmp_path)))
    assert data["duration_seconds"] == pytest.approx(2.0, abs=0.25)


def test_video_only_trim(tmp_path):
    clip = make_test_clip(tmp_path / "mute.mp4", duration=3.0, with_audio=False)
    data = _ok(call_tool(media_trim, str(clip), 0.5, output_dir=str(tmp_path / "o")))
    assert data["has_audio"] is False and data["duration_seconds"] == pytest.approx(2.5, abs=0.1)


def test_concat_reencodes_mixed_sources(tmp_path):
    import json
    data = _ok(call_tool(media_concat, json.dumps([str(FIX / "test_clip_1080p2997_5s.mp4"),
                                                   str(FIX / "test_audio_with_silence.mp4")]),
                         output_dir=str(tmp_path)))
    assert data["method"] == "reencode"
    assert data["duration_seconds"] == pytest.approx(10.0, abs=0.1)
    assert (data["width"], data["height"], data["channels"], data["sample_rate"]) == (1920, 1080, 2, 48000)


def test_concat_silent_source_gets_silence(tmp_path):
    import json
    data = _ok(call_tool(media_concat, json.dumps([str(FIX / "test_clip_1080p2997_5s.mp4"),
                                                   str(FIX / "greenscreen_reporter_720.mp4")]),
                         output_dir=str(tmp_path)))
    expected = probe_media(FIX / "test_clip_1080p2997_5s.mp4").duration_seconds + \
        probe_media(FIX / "greenscreen_reporter_720.mp4").duration_seconds
    assert data["has_audio"] and data["duration_seconds"] == pytest.approx(expected, abs=0.15)


def test_concat_identical_files_copies(tmp_path):
    import json
    clip = make_test_clip(tmp_path / "same.mp4", duration=1.0, with_audio=True)
    data = _ok(call_tool(media_concat, json.dumps([str(clip), str(clip)]), output_dir=str(tmp_path / "o")))
    assert data["method"] == "copy" and data["duration_seconds"] == pytest.approx(2.0, abs=0.15)


def test_protected_output_is_refused(tmp_path):
    raw = tmp_path / "ws" / "media" / "raw"
    raw.mkdir(parents=True)
    result = call_tool(media_trim, str(FIX / "test_clip_1080p2997_5s.mp4"), 1.0, end_seconds=2.0, output_dir=str(raw))
    assert result["status"] == "error" and result["error_type"] == "invalid_input"
    assert list(raw.iterdir()) == []


def test_errors(tmp_path):
    assert call_tool(media_trim, str(tmp_path / "nope.mp4"), 0.0)["error_type"] == "missing_file"
    bad = call_tool(media_trim, str(FIX / "test_clip_1080p2997_5s.mp4"), 9.0, output_dir=str(tmp_path))
    assert bad["error_type"] == "invalid_input" and "past the end" in bad["message"]
    assert call_tool(media_concat, "[oops", output_dir=str(tmp_path))["error_type"] == "bad_json_param"
    assert call_tool(media_concat, '["a.mp4"]')["error_type"] == "invalid_input"
