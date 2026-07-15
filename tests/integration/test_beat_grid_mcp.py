"""ffmpeg-gated proof for the music beat-grid MCP tools.

Synthesises a metronome click track at exactly 120 BPM with ffmpeg (sine bursts
every 0.5 s), then asserts ``music_beat_grid`` recovers 120 +/- 2 BPM with beat
times within +/-50 ms of the true grid, and ``markers_from_beats`` writes bar
markers.  Lives in ``tests/integration/`` (local ffmpeg only -- no network),
auto-skipped when ffmpeg is absent.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

import workshop_video_brain.server as _server  # noqa: F401
from workshop_video_brain.edit_mcp.server.bundles import beat_grid as _bundle
import workshop_video_brain.edit_mcp.server.tools as _tools

ffmpeg_available = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg not available on PATH"
)

TRUE_BPM = 120.0
PERIOD = 60.0 / TRUE_BPM  # 0.5 s
BEAT_TOLERANCE = 0.05      # +/-50 ms


from tests._testkit import unwrap as _fn  # noqa: E402


music_beat_grid = _fn(_bundle.music_beat_grid)
markers_from_beats = _fn(_bundle.markers_from_beats)
workspace_create = _fn(_tools.workspace_create)


def _make_ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Beat Test", media_root=str(media_root))
    assert result["status"] == "success", result
    return Path(result["data"]["workspace_root"])


def _render_click_track(path: Path, bpm: float = TRUE_BPM, seconds: float = 8.0) -> None:
    """Render a 120 BPM metronome: 40 ms sine bursts on every beat."""
    period = 60.0 / bpm
    n_beats = int(seconds / period)
    gates = []
    for k in range(n_beats):
        t0 = k * period
        gates.append(f"between(t,{t0:.4f},{t0 + 0.04:.4f})")
    expr = "0.8*sin(2*PI*1000*t)*(" + "+".join(gates) + ")"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=44100:d={seconds}",
        "-ac", "1", str(path),
    ]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_tools_registered():
    lister = getattr(_server.mcp, "list_tools", None) or _server.mcp.get_tools
    result = asyncio.run(lister())
    names = set(result.keys()) if isinstance(result, dict) else {
        getattr(t, "name", t) for t in result
    }
    for name in ("music_beat_grid", "markers_from_beats"):
        assert name in names, f"{name} not registered"


# ---------------------------------------------------------------------------
# Beat grid recovery
# ---------------------------------------------------------------------------

def test_music_beat_grid_recovers_120_bpm(tmp_path):
    ws = _make_ws(tmp_path)
    click = ws / "media" / "raw" / "click_120.wav"
    click.parent.mkdir(parents=True, exist_ok=True)
    _render_click_track(click)

    out = music_beat_grid(workspace_path=str(ws), source=str(click))
    assert out["status"] == "success", out
    data = out["data"]

    # (1) BPM within +/-2 of 120.
    assert abs(data["bpm_estimate"] - TRUE_BPM) <= 2.0, data["bpm_estimate"]

    # (2) every beat within +/-50 ms of a true 0.5 s grid position.
    beats = data["beats"]
    assert len(beats) >= 12, beats
    for b in beats:
        nearest = round(b / PERIOD) * PERIOD
        assert abs(b - nearest) <= BEAT_TOLERANCE, (b, nearest)

    # Report written to reports/beat_grid.json.
    report = Path(data["report_path"])
    assert report == ws / "reports" / "beat_grid.json"
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["bpm_estimate"] == data["bpm_estimate"]
    assert saved["onsets"]


def test_markers_from_beats_writes_bar_markers(tmp_path):
    ws = _make_ws(tmp_path)
    click = ws / "media" / "raw" / "click_120.wav"
    click.parent.mkdir(parents=True, exist_ok=True)
    _render_click_track(click)

    grid = music_beat_grid(workspace_path=str(ws), source=str(click))
    assert grid["status"] == "success", grid

    out = markers_from_beats(workspace_path=str(ws), every_n=4, category="beat")
    assert out["status"] == "success", out
    data = out["data"]
    assert data["category"] == "beat"
    assert data["marker_count"] >= 3

    marker_path = Path(data["marker_path"])
    assert marker_path == ws / "markers" / "beat_markers.json"
    saved = json.loads(marker_path.read_text(encoding="utf-8"))
    assert len(saved) == data["marker_count"]
    # Bars are one period * every_n apart (~2.0 s for 4 beats at 120 BPM).
    times = [m["start_seconds"] for m in saved]
    if len(times) >= 2:
        assert abs((times[1] - times[0]) - 4 * PERIOD) <= BEAT_TOLERANCE


def test_music_beat_grid_missing_source_errors(tmp_path):
    ws = _make_ws(tmp_path)
    out = music_beat_grid(workspace_path=str(ws), source="nope.wav")
    assert out["status"] == "error"
