"""`media_transcode_cfr` must not call every ffmpeg failure a bug.

Every non-zero ffmpeg exit reached ``from_exception`` as a bare ``RuntimeError``
and came back as ``operation_failed`` -- "This is an unexpected error. Please
report it". A file the user handed in that is not decodable video is not
unexpected, and neither is an ffmpeg that is not installed; telling people to
open an issue about their own media is worse than saying nothing.

What is deliberately **not** done here: classify by matching ffmpeg's stderr
text. ``adapters/render/media_check`` already argued that case against melt --
the wording is not part of the tool's API, it varies by version and build, and
it cannot distinguish a fatal cause from a benign warning. Every verdict below
instead rests on something this code can determine for itself *after* the
failure: can ffprobe read the source, and can the output directory be written.
Anything else is reported as genuinely undetermined, saying so in those words.

The post-mortem runs only after ffmpeg has already failed, never as a
precondition, so it cannot refuse a transcode that would have worked.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegNotFound,
    FFmpegResult,
)
from workshop_video_brain.edit_mcp.server.tools.workspace_media import (
    media_transcode_cfr,
)

_RUN = "workshop_video_brain.edit_mcp.pipelines.vfr_check.run_ffmpeg"
_PROBE = "workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media"

# Cases that shell out to a real ffmpeg -- they skip in the no-binaries unit
# gate and run in the full suite (see CLAUDE.md, "CI").
requires_real_ffmpeg = requires_ffmpeg_ffprobe


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    for sub in ("media/raw", "media/processed", "projects/working_copies", "reports"):
        (ws / sub).mkdir(parents=True)
    return ws


def _failed(stderr: str) -> FFmpegResult:
    return FFmpegResult(
        success=False,
        input_path="in",
        output_path="out",
        command=["ffmpeg"],
        stderr=stderr,
    )


def _real_clip(path: Path, *, seconds: int = 1) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=30:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True, timeout=60,
    )


def _suggestion(result: dict) -> str:
    return result.get("suggestion", "")


# ---------------------------------------------------------------------------
# What the user can act on
# ---------------------------------------------------------------------------


@requires_real_ffmpeg
def test_an_undecodable_source_is_not_reported_as_a_bug(
    workspace: Path,
) -> None:
    source = workspace / "media" / "processed" / "notvideo.mp4"
    source.write_bytes(b"this is not a video file at all")

    result = call_tool(
        media_transcode_cfr, workspace_path=str(workspace), file_path=str(source)
    )

    assert result["status"] == "error"
    assert result["error_type"] == "media_unreadable"
    assert "report" not in _suggestion(result).lower()
    assert str(source) in result["message"] or str(source) in result.get("path", "")


@requires_real_ffmpeg
def test_an_undecodable_source_still_carries_ffmpegs_own_words(
    workspace: Path,
) -> None:
    """Naming the cause is what makes the error actionable; the classification
    must not throw ffmpeg's own reason away."""
    source = workspace / "media" / "processed" / "notvideo.mp4"
    source.write_bytes(b"this is not a video file at all")

    # An explicit target_fps skips the up-front probe, so ffmpeg really runs and
    # really fails -- this exercises the post-mortem path, not the probe path.
    result = call_tool(
        media_transcode_cfr,
        workspace_path=str(workspace),
        file_path=str(source),
        target_fps=30,
    )

    assert result["error_type"] == "media_unreadable"
    blob = " ".join(str(v) for v in result.values())
    assert "Invalid data found when processing input" in blob


def test_a_missing_ffmpeg_is_an_install_problem_not_a_missing_media_file(
    workspace: Path,
) -> None:
    source = workspace / "media" / "processed" / "clip.mp4"
    source.write_bytes(b"x")

    with patch(_RUN, side_effect=FFmpegNotFound("ffmpeg binary not found on PATH")):
        result = call_tool(
            media_transcode_cfr,
            workspace_path=str(workspace),
            file_path=str(source),
            target_fps=30,
        )

    assert result["status"] == "error"
    assert result["error_type"] == "missing_binary"
    assert "report" not in _suggestion(result).lower()


def test_an_unwritable_destination_is_named(workspace: Path) -> None:
    holder = workspace / "media" / "processed" / "locked"
    holder.mkdir()
    source = holder / "clip.mp4"
    source.write_bytes(b"x")
    os.chmod(holder, 0o555)
    try:
        with patch(_RUN, return_value=_failed("Permission denied")), patch(
            _PROBE
        ) as probe:
            probe.return_value.fps = 30.0
            result = call_tool(
                media_transcode_cfr,
                workspace_path=str(workspace),
                file_path=str(source),
                target_fps=30,
            )
    finally:
        os.chmod(holder, 0o755)

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert str(holder) in result["message"]
    assert "report" not in _suggestion(result).lower()


def test_a_source_that_is_not_there_is_a_missing_file(workspace: Path) -> None:
    result = call_tool(
        media_transcode_cfr,
        workspace_path=str(workspace),
        file_path=str(workspace / "media" / "processed" / "gone.mp4"),
    )
    assert result["status"] == "error"
    assert result["error_type"] == "missing_file"
    assert "report" not in _suggestion(result).lower()


# ---------------------------------------------------------------------------
# What is genuinely unknown -- said in those words
# ---------------------------------------------------------------------------


def test_an_undetermined_failure_says_so_rather_than_blaming_the_media(
    workspace: Path,
) -> None:
    """Source probes fine, destination is writable, ffmpeg still failed. The
    honest answer is "we could not tell" -- not "your file is unreadable"."""
    source = workspace / "media" / "processed" / "clip.mp4"
    source.write_bytes(b"x")

    with patch(_RUN, return_value=_failed("Unknown encoder 'libfoo'")), patch(
        _PROBE
    ) as probe:
        probe.return_value.fps = 30.0
        result = call_tool(
            media_transcode_cfr,
            workspace_path=str(workspace),
            file_path=str(source),
            target_fps=30,
        )

    assert result["status"] == "error"
    assert result["error_type"] == "operation_failed"
    assert result["error_type"] != "media_unreadable"
    # ffmpeg's own last words survive -- they may name something fixable.
    blob = " ".join(str(v) for v in result.values())
    assert "Unknown encoder 'libfoo'" in blob
    # And the suggestion admits the cause was not determined.
    assert "could not" in _suggestion(result).lower()


def test_an_undetermined_failure_does_not_claim_the_source_is_unreadable(
    workspace: Path,
) -> None:
    """Accept control for the source verdict: a readable source must never be
    blamed. A guard that answers "bad media" to everything passes the first
    test in this file and is useless."""
    source = workspace / "media" / "processed" / "clip.mp4"
    source.write_bytes(b"x")

    with patch(_RUN, return_value=_failed("No space left on device")), patch(
        _PROBE
    ) as probe:
        probe.return_value.fps = 30.0
        result = call_tool(
            media_transcode_cfr,
            workspace_path=str(workspace),
            file_path=str(source),
            target_fps=30,
        )

    assert result["error_type"] != "media_unreadable"
    assert "not a valid media file" not in result["message"].lower()


def test_an_undeterminable_probe_does_not_blame_the_source(
    workspace: Path,
) -> None:
    """If ffprobe itself cannot run, we do not know whether the source is
    readable, so we must not say that it isn't."""
    source = workspace / "media" / "processed" / "clip.mp4"
    source.write_bytes(b"x")

    with patch(_RUN, return_value=_failed("something went wrong")), patch(
        _PROBE, side_effect=FFmpegNotFound("ffprobe binary not found on PATH")
    ):
        result = call_tool(
            media_transcode_cfr,
            workspace_path=str(workspace),
            file_path=str(source),
            target_fps=30,
        )

    assert result["status"] == "error"
    assert result["error_type"] != "media_unreadable"


# ---------------------------------------------------------------------------
# Accept controls: nothing here may refuse work that succeeds
# ---------------------------------------------------------------------------


@requires_real_ffmpeg
def test_a_good_transcode_still_succeeds(workspace: Path) -> None:
    source = workspace / "media" / "processed" / "clip.mp4"
    _real_clip(source)

    result = call_tool(
        media_transcode_cfr,
        workspace_path=str(workspace),
        file_path=str(source),
        target_fps=24,
    )

    assert result["status"] == "success", result
    out = Path(result["data"]["output_path"])
    assert out.exists() and out.stat().st_size > 0


@requires_real_ffmpeg
def test_a_good_transcode_with_auto_fps_still_succeeds(workspace: Path) -> None:
    source = workspace / "media" / "processed" / "clip.mp4"
    _real_clip(source)

    result = call_tool(
        media_transcode_cfr, workspace_path=str(workspace), file_path=str(source)
    )

    assert result["status"] == "success", result


def test_a_timeout_is_still_reported_as_a_timeout(workspace: Path) -> None:
    """Accept control: the new classification must not swallow the failures the
    error contract already identified."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegTimeout

    source = workspace / "media" / "processed" / "clip.mp4"
    source.write_bytes(b"x")

    with patch(_RUN, side_effect=FFmpegTimeout("ffmpeg timed out after 3600s")):
        result = call_tool(
            media_transcode_cfr,
            workspace_path=str(workspace),
            file_path=str(source),
            target_fps=30,
        )

    assert result["status"] == "error"
    assert "timed out" in result["message"].lower()
    assert result.get("binary") == "ffmpeg"
