"""Run the auto-editor CLI and read its cut list.

Only the timeline v3 JSON is read. auto-editor's ``--export kdenlive`` is never
imported, because it bypasses the serializer's rules. See
``vault/wiki/auto-editor-cut-list.md``.

The pip package is a launcher that downloads a native binary on first run. This
adapter only looks for that binary and never triggers the download.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS,
    _stderr_tail,
)


class AutoEditorError(RuntimeError):
    """auto-editor exited nonzero, or its v3 output is missing or unusable."""


def resolve_binary() -> Path | None:
    """Return the downloaded binary beside the package, else one on PATH, else None."""
    spec = importlib.util.find_spec("auto_editor")
    for location in getattr(spec, "submodule_search_locations", None) or []:
        for name in ("auto-editor", "auto-editor.exe"):
            candidate = Path(location) / "bin" / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    found = shutil.which("auto-editor")
    # A PATH hit inside a venv can be the pip launcher, which would download.
    # Only trust it when the package is absent, so it must be a system install.
    return Path(found) if found and spec is None else None


def build_command(
    binary: Path | str,
    source: Path | str,
    out_v3: Path | str,
    *,
    threshold_linear: float,
    margin_seconds: float,
    temp_dir: Path | str,
) -> list[str]:
    """Build the analysis-only command; ``--export v3`` is what writes the cut list."""
    return [
        str(binary), str(source),
        "--edit", f"audio:threshold={threshold_linear:.6f}",
        "--margin", f"{margin_seconds:g}s",
        "--export", "v3",
        "-o", str(out_v3),
        "--temp-dir", str(temp_dir),
        "--progress", "none",
        "--no-open",
    ]


def run_v3(source: Path, *, threshold_db: float = -30.0, margin_seconds: float = 0.2) -> dict:
    """Run auto-editor on *source* and return its parsed v3 JSON.

    Raises :class:`AutoEditorError` on failure. ``subprocess.TimeoutExpired``
    propagates unchanged: ``tool_guard`` turns it into a "timed out" error that
    names auto-editor rather than ffmpeg.
    """
    binary = resolve_binary()
    if binary is None:
        raise AutoEditorError("auto-editor binary not found; run `auto-editor --version` once to fetch it.")
    with tempfile.TemporaryDirectory(prefix="wvb-auto-editor-") as scratch:
        scratch_dir = Path(scratch)
        out_v3 = scratch_dir / "cut.v3"
        work_dir = scratch_dir / "work"
        command = build_command(
            binary, source, out_v3,
            threshold_linear=10 ** (threshold_db / 20),
            margin_seconds=margin_seconds,
            temp_dir=work_dir,
        )
        proc = subprocess.run(
            command, capture_output=True, text=True, check=False,
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
        if proc.returncode != 0:
            raise AutoEditorError(
                f"auto-editor failed (rc={proc.returncode}): {_stderr_tail(proc.stderr or proc.stdout or '', 6)}"
            )
        if not out_v3.is_file():
            written = sorted(scratch_dir.glob("*.v3"))
            if not written:
                raise AutoEditorError("auto-editor exited 0 but wrote no .v3 cut list.")
            out_v3 = written[0]
        try:
            return json.loads(out_v3.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise AutoEditorError(f"auto-editor wrote an unreadable cut list: {exc}") from exc


def keep_ranges_from_v3(v3: dict) -> list[tuple[float, float]]:
    """Convert a v3 timeline to sorted, merged ``(start, end)`` source seconds to keep.

    Clips count in timebase frames: ``offset`` is the source in-frame and ``dur``
    the length. The first non-empty video layer wins, else the first audio layer.
    A speed-changed clip raises, because its range is not a plain cut.
    """
    try:
        timebase = Fraction(str(v3["timebase"]))
        layers = [*v3.get("v", []), *v3.get("a", [])]
        clips = next((layer for layer in layers if layer), [])
        ranges = []
        for clip in clips:
            if float(clip.get("speed", 1)) != 1:
                raise AutoEditorError(f"auto-editor cut list has a speed-changed clip: {clip.get('speed')}")
            start = Fraction(int(clip["offset"])) / timebase
            end = Fraction(int(clip["offset"]) + int(clip["dur"])) / timebase
            ranges.append((start, end))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise AutoEditorError(f"auto-editor cut list has an unexpected shape: {exc}") from exc

    merged: list[tuple[Fraction, Fraction]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [(round(float(start), 6), round(float(end), 6)) for start, end in merged]
