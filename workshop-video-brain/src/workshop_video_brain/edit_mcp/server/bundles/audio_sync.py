"""``media_sync_by_audio`` MCP tool -- recover the time offset between two
recordings of the same event (multicam angles, lav mic vs camera audio).

Auto-imported by ``server/bundles/__init__.py``; registers one tool on the
shared FastMCP singleton.  Read-only analysis: it decodes audio for
measurement and writes nothing to the workspace.  Returns an ``_ok`` / ``_err``
result dict.  Phase A of the multicam spec
(``docs/research/2026-07-03-tutorial-effect-analysis/multicam.md``).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.audio_sync import (
    DEFAULT_WINDOW_SECONDS,
    sync_by_audio,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp


def _resolve(workspace_path: Path, source: str) -> Path:
    """Resolve a source path against the workspace root when relative."""
    p = Path(source)
    if not p.is_absolute():
        p = workspace_path / source
    return p


@mcp.tool()
def media_sync_by_audio(
    workspace_path: str,
    source_a: str,
    source_b: str,
    method: str = "correlate",
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> dict:
    """Find the time offset between two recordings of the same event.

    Given two files that captured the same sound (two camera angles, a lav mic
    and camera audio, a screen recording and a webcam), estimate how far apart
    they start so the clips can be stacked in sync on the timeline. This is the
    audio-align step of a multicam workflow.

    Methods:
      * ``correlate`` (default, always available) -- decode a low-rate mono
        energy/onset envelope from each file with FFmpeg and cross-correlate
        them. Pure NumPy, no third-party audio libraries.
      * ``chromaprint`` -- use FFmpeg's ``chromaprint`` muxer to fingerprint
        each file and correlate the raw fingerprints. Only works when the local
        FFmpeg build ships the ``chromaprint`` muxer; otherwise returns an
        actionable error telling you to install it or use ``correlate``.

    The returned ``offset_seconds`` is the start of ``source_b`` relative to
    ``source_a``: positive means an event appears that many seconds *later* into
    ``source_b`` (it has that much extra lead-in). To align, shift ``source_b``
    left by ``offset_seconds`` (or ``source_a`` right by the same).
    ``confidence`` is a normalized correlation coefficient in ``[0, 1]``.

    Args:
        workspace_path: Path to workspace root.
        source_a: Reference recording (absolute, or relative to the workspace).
        source_b: Second recording of the same event.
        method: ``"correlate"`` or ``"chromaprint"``.
        window_seconds: Analyse at most this many leading seconds of each file
            (default 120). Smaller = faster; larger = more common material to
            lock onto.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))

    if not source_a or not source_a.strip() or not source_b or not source_b.strip():
        return _err("Both source_a and source_b are required.")

    src_a = _resolve(ws_path, source_a)
    src_b = _resolve(ws_path, source_b)

    result = sync_by_audio(
        src_a,
        src_b,
        method=method,
        window_seconds=window_seconds,
    )
    if not result.get("success"):
        return _err(result.get("error", "Audio sync failed"))

    data = {k: v for k, v in result.items() if k != "success"}
    return _ok(data)
