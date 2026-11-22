"""Single-file VFR check (ROADMAP next #6 (c)).

``media_check_vfr`` only scanned a whole workspace, so there was no way to
check one recording before ingest -- although the handbook (Ch.14) documents
``media_check_vfr file="screen-recording.mp4"``. These run real ffmpeg/ffprobe
on generated media; nothing is mocked.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.pipelines import vfr_check
from workshop_video_brain.edit_mcp.server.tools.workspace_media import media_check_vfr

pytestmark = requires_ffmpeg_ffprobe


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args],
        check=True, capture_output=True, timeout=60,
    )


def _make_vfr(path: Path) -> Path:
    # First second at 30 fps, then frames spaced twice as far apart.
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=s=64x64:r=30:d=2",
        "-vf", "setpts='if(lt(N,30),N,30+(N-30)*2)/30/TB'",
        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    )
    return path


def _make_cfr(path: Path) -> Path:
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc=s=64x64:r=30:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    )
    return path


# ---------------------------------------------------------------------------
# Pipeline: check_vfr_file
# ---------------------------------------------------------------------------

def test_vfr_file_outside_any_workspace(tmp_path):
    src = _make_vfr(tmp_path / "phone.mp4")
    # A CFR neighbour must not be scanned: this checks one file, not a folder.
    _make_cfr(tmp_path / "other.mp4")

    report = vfr_check.check_vfr_file(src)

    assert report.files_checked == 1
    assert report.all_cfr is False
    assert [v.path for v in report.vfr_files] == [str(src)]
    vf = report.vfr_files[0]
    assert vf.divergence_pct > 5.0
    assert vf.r_frame_rate not in ("", "0/1")
    assert "media_transcode_cfr" in vf.suggested_action


def test_cfr_file_is_all_cfr(tmp_path):
    report = vfr_check.check_vfr_file(_make_cfr(tmp_path / "cam.mp4"))
    assert report.files_checked == 1
    assert report.all_cfr is True
    assert report.vfr_files == [] and report.unprobed_files == []


def test_vfr_file_with_cfr_copy_is_resolved(tmp_path):
    src = _make_vfr(tmp_path / "phone.mp4")
    copy = _make_cfr(vfr_check.cfr_sibling(src))

    report = vfr_check.check_vfr_file(src)

    assert report.all_cfr is True
    assert report.vfr_files == []
    assert [(r.path, r.cfr_copy) for r in report.resolved_files] == [(str(src), str(copy))]


def test_vfr_copy_does_not_resolve(tmp_path):
    src = _make_vfr(tmp_path / "phone.mp4")
    _make_vfr(vfr_check.cfr_sibling(src))

    report = vfr_check.check_vfr_file(src)

    assert report.all_cfr is False
    assert len(report.vfr_files) == 1 and report.resolved_files == []


def test_unreadable_file_is_unprobed(tmp_path):
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video")

    report = vfr_check.check_vfr_file(bad)

    assert report.files_checked == 0
    assert report.all_cfr is False
    assert [u.path for u in report.unprobed_files] == [str(bad)]


def test_audio_only_file_is_not_reported_cfr(tmp_path):
    """No video stream -> no frame rate. That is not a confirmed CFR file."""
    wav = tmp_path / "voice.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=d=1", str(wav))

    report = vfr_check.check_vfr_file(wav)

    assert report.all_cfr is False
    assert len(report.unprobed_files) == 1
    assert "No video stream" in report.unprobed_files[0].error


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        vfr_check.check_vfr_file(tmp_path / "nope.mp4")


# ---------------------------------------------------------------------------
# MCP tool: media_check_vfr(file_path=...)
# ---------------------------------------------------------------------------

def test_tool_checks_one_file_without_workspace(tmp_path):
    src = _make_vfr(tmp_path / "phone.mp4")

    result = call_tool(media_check_vfr, file_path=str(src))

    assert result["status"] == "success", result
    data = result["data"]
    assert data["files_checked"] == 1
    assert data["all_cfr"] is False
    assert [v["path"] for v in data["vfr_files"]] == [str(src)]


def test_tool_relative_file_reads_against_workspace(tmp_path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    _make_vfr(raw / "a.mp4")
    _make_cfr(raw / "b.mp4")

    result = call_tool(media_check_vfr, workspace_path=str(tmp_path),
                       file_path="media/raw/b.mp4")

    assert result["status"] == "success", result
    assert result["data"]["files_checked"] == 1
    assert result["data"]["all_cfr"] is True


def test_tool_relative_file_without_workspace_is_refused(tmp_path):
    result = call_tool(media_check_vfr, file_path="phone.mp4")
    assert result["status"] == "error"
    assert "relative" in result["message"]


def test_tool_missing_file(tmp_path):
    result = call_tool(media_check_vfr, file_path=str(tmp_path / "nope.mp4"))
    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_tool_directory_as_file_is_refused(tmp_path):
    result = call_tool(media_check_vfr, file_path=str(tmp_path))
    assert result["status"] == "error"
    assert "directory" in result["message"]


def test_tool_workspace_scan_unchanged(tmp_path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    _make_vfr(raw / "a.mp4")
    _make_cfr(raw / "b.mp4")

    result = call_tool(media_check_vfr, str(tmp_path))

    assert result["status"] == "success", result
    assert result["data"]["files_checked"] == 2
    assert len(result["data"]["vfr_files"]) == 1


def test_tool_with_neither_argument_is_an_error():
    result = call_tool(media_check_vfr)
    assert result["status"] == "error"
