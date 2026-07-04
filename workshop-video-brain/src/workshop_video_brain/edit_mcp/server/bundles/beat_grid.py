"""Music beat-grid MCP tools: ``music_beat_grid`` / ``markers_from_beats``.

Gap-analysis item 9 ("Music beat alignment"): pacing_analyze covers *speech*
rhythm; this adds an onset/beat grid from a *music* track so cuts and assembly
can snap to the beat.

* ``music_beat_grid`` decodes a source track and runs pure-NumPy onset + tempo
  detection (``pipelines/beat_grid.py``; no ``librosa``), writing
  ``reports/beat_grid.json`` and returning ``{bpm_estimate, beats, onsets}``.
* ``markers_from_beats`` turns every N-th beat (a bar) into workspace markers
  (``markers/beat_markers.json``) so ``timeline_build`` / assembly and future
  cut tools can snap to them.

Registered by the ``bundles`` package auto-importer.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_binary,
    invalid_input,
    MISSING_FILE,
    NOT_FOUND,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _require_workspace,
)
from workshop_video_brain.edit_mcp.pipelines import beat_grid as _bg
from workshop_video_brain.edit_mcp.pipelines.audio_sync import ffmpeg_available


def _resolve_source(ws_path: Path, source: str) -> Path | None:
    """Resolve *source* against absolute path or workspace media roots."""
    p = Path(source)
    if p.is_absolute():
        return p if p.exists() else None
    for base in (ws_path, ws_path / "media" / "raw", ws_path / "media", ws_path / "media" / "processed"):
        cand = base / source
        if cand.exists():
            return cand
    return None


@mcp.tool()
@tool_guard
def music_beat_grid(
    workspace_path: str,
    source: str,
    sensitivity: float = 0.5,
) -> dict:
    """Detect onsets, tempo, and a beat grid for a music track (pure NumPy).

    Args:
        workspace_path: Workspace root directory.
        source: Music file (absolute, or resolved under the workspace / media/).
        sensitivity: ``[0, 1]`` onset-picking sensitivity -- higher finds more
            onsets (default 0.5).

    Writes ``reports/beat_grid.json`` and returns ``bpm_estimate``, the ``beats``
    grid (seconds), raw ``onsets`` (seconds), and analysis metadata.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if not ffmpeg_available():
        return missing_binary("ffmpeg", "apt install ffmpeg (Debian/Ubuntu) or brew install ffmpeg (macOS).")
    if not 0.0 <= float(sensitivity) <= 1.0:
        return err(f"sensitivity must be in [0.0, 1.0]; got {sensitivity}", suggestion="Pass sensitivity as a fraction between 0.0 (only strong beats) and 1.0 (every beat).")

    src = _resolve_source(ws_path, source)
    if src is None:
        return err(f"Source not found: {source}", error_type=MISSING_FILE, suggestion="Check the source path; it resolves under the workspace root unless absolute.", path=str(source))

    try:
        result = _bg.analyze_beats(src, sensitivity=sensitivity)
    except RuntimeError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    result["source"] = str(src)
    reports_dir = ws_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "beat_grid.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    data = dict(result)
    data["report_path"] = str(out_path)
    return _ok(data)


@mcp.tool()
@tool_guard
def markers_from_beats(
    workspace_path: str,
    beat_file: str = "",
    every_n: int = 4,
    category: str = "beat",
) -> dict:
    """Convert a beat grid into workspace bar markers (every N-th beat = a bar).

    Args:
        workspace_path: Workspace root directory.
        beat_file: Beat-grid JSON to read (absolute or workspace-relative).
            Defaults to ``reports/beat_grid.json`` from ``music_beat_grid``.
        every_n: Emit a marker every ``every_n`` beats (a musical bar; default 4).
        category: Marker category tag for the bars (default ``"beat"``).

    Writes ``markers/beat_markers.json`` and returns the marker count + path.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if every_n < 1:
        return err("every_n must be >= 1", suggestion="Pass every_n as 1 or more (place a marker on every Nth beat).")

    if beat_file:
        bf = Path(beat_file)
        if not bf.is_absolute():
            bf = ws_path / beat_file
    else:
        bf = ws_path / "reports" / "beat_grid.json"
    if not bf.exists():
        return err(f"Beat-grid file not found: {bf}", suggestion="Check the beat-grid path; it resolves under the workspace root unless absolute.")

    try:
        payload = json.loads(bf.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return err(f"Could not read beat file: {exc}", suggestion="Make sure the beat file is valid JSON produced by the beat-detection step.")

    beats = payload.get("beats", []) if isinstance(payload, dict) else payload
    if not isinstance(beats, list) or not beats:
        return err("Beat file has no beats", error_type=NOT_FOUND, suggestion="Re-run music_beat_grid on a music track first; a valid beat grid has a non-empty beats list.")

    markers = _bg.beats_to_bar_markers(beats, every_n=every_n, category=category)
    markers_dir = ws_path / "markers"
    markers_dir.mkdir(parents=True, exist_ok=True)
    out_path = markers_dir / "beat_markers.json"
    out_path.write_text(json.dumps(markers, indent=2), encoding="utf-8")

    return _ok(
        {
            "marker_path": str(out_path),
            "marker_count": len(markers),
            "every_n": every_n,
            "category": category,
            "beat_count": len(beats),
            "bar_times": [m["start_seconds"] for m in markers],
        }
    )
