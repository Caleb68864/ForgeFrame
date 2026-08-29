"""``tool_guard`` / ``from_exception`` classify child-process environment
failures (timeouts, missing ffmpeg) as *known* conditions -- never with the
"unexpected error, please report it" voice reserved for real bugs.

Every subprocess site in the source tree now carries ``timeout=`` (enforced by
``test_subprocess_timeouts.py``), so a ``TimeoutExpired`` is the normal way an
oversized or wedged job surfaces to the user. That surface must be actionable.
"""
from __future__ import annotations

import logging
import subprocess

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegNotFound,
    FFmpegTimeout,
)
from workshop_video_brain.edit_mcp.server.errors import (
    MISSING_BINARY,
    OPERATION_FAILED,
    from_exception,
    tool_guard,
)


def _guarded(exc: BaseException):
    @tool_guard
    def tool(workspace_path: str):
        raise exc

    return tool("ws")


def test_timeout_expired_is_actionable_not_please_report(caplog):
    exc = subprocess.TimeoutExpired(["ffmpeg", "-i", "big.mp4"], 600)
    with caplog.at_level(logging.WARNING):
        out = _guarded(exc)

    assert out["status"] == "error"
    assert out["error_type"] == OPERATION_FAILED
    assert "ffmpeg timed out after 600s" in out["message"]
    assert out["timed_out_after"] == 600.0
    assert out["binary"] == "ffmpeg"
    assert "report" not in out["suggestion"].lower()
    assert "proxy" in out["suggestion"]
    # Known condition -> WARNING with one-line cause, no traceback dump.
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert not any(r.exc_info for r in caplog.records)


def test_runner_ffmpeg_timeout_is_classified():
    out = _guarded(FFmpegTimeout("ffmpeg timed out after 3600s (elapsed 3600.2s)"))
    assert out["error_type"] == OPERATION_FAILED
    assert out["binary"] == "ffmpeg"
    assert "3600s" in out["message"]
    assert "report" not in out["suggestion"].lower()


def test_ffmpeg_not_found_maps_to_missing_binary():
    out = _guarded(FFmpegNotFound("ffprobe binary not found on PATH (probing x.mp4)."))
    assert out["error_type"] == MISSING_BINARY
    assert out["binary"] == "ffprobe"
    assert "PATH" in out["suggestion"]


def test_from_exception_shares_the_classification():
    out = from_exception(subprocess.TimeoutExpired("melt", 30))
    assert out["error_type"] == OPERATION_FAILED
    assert out["timed_out_after"] == 30.0
    assert out["binary"] == "melt"


def test_unrelated_exception_still_takes_the_backstop_path(caplog):
    with caplog.at_level(logging.ERROR):
        out = _guarded(RuntimeError("boom"))
    assert out["error_type"] == OPERATION_FAILED
    assert "unexpectedly" in out["message"]
    assert "report" in out["suggestion"].lower()
    assert any(r.exc_info for r in caplog.records)
