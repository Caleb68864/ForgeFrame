"""ffmpeg-gated proof for the voiceover-loop MCP tools.

Runs ``vo_plan`` on a 3-section fixture script (asserting 3 cues, a written
checklist, and markers/guides), then ``vo_attach`` on an ffmpeg-generated sine
"take" (asserting the take is placed at the right frame in the project XML and
drift is reported), then ``vo_status``.  Lives in ``tests/integration/`` (local
ffmpeg only); auto-skipped when ffmpeg is absent.
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
from workshop_video_brain.edit_mcp.server.bundles import vo_loop as _bundle
import workshop_video_brain.edit_mcp.server.tools as _tools
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.pipelines.vo_loop import audio_playlists

ffmpeg_available = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg not available on PATH"
)


def _fn(tool):
    return getattr(tool, "fn", tool)


vo_plan = _fn(_bundle.vo_plan)
vo_attach = _fn(_bundle.vo_attach)
vo_status = _fn(_bundle.vo_status)
workspace_create = _fn(_tools.workspace_create)

SCRIPT = """# Introduction
Welcome to this quick woodworking build where we make a small shelf together.

# Building The Frame
Cut the plywood panels to length and glue the frame corners with wood glue.

# Wrapping Up
Sand the edges, add a coat of finish, and your shelf is ready to hang.
"""

# Minimal project with one video track and one audio track (hide="video").
PROJECT_XML = """<?xml version="1.0" encoding="utf-8"?>
<mlt title="VO Test" version="7" producer="main_bin">
  <profile width="1920" height="1080" frame_rate_num="30" frame_rate_den="1" colorspace="709"/>
  <playlist id="playlist0"/>
  <playlist id="playlist_audio0"/>
  <tractor id="tractor0" in="0" out="299">
    <track producer="playlist0"/>
    <track producer="playlist_audio0" hide="video"/>
  </tractor>
</mlt>
"""


def _make_ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="VO Test", media_root=str(media_root))
    assert result["status"] == "success", result
    return Path(result["data"]["workspace_root"])


def _write_script(ws: Path) -> str:
    p = ws / "script.md"
    p.write_text(SCRIPT, encoding="utf-8")
    return "script.md"


def _write_project(ws: Path, name: str = "vo.kdenlive") -> str:
    (ws / name).write_text(PROJECT_XML, encoding="utf-8")
    return name


def _render_sine_take(path: Path, seconds: float) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
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
    for name in ("vo_plan", "vo_attach", "vo_status"):
        assert name in names, f"{name} not registered"


# ---------------------------------------------------------------------------
# vo_plan -> markers
# ---------------------------------------------------------------------------

def test_vo_plan_three_cues_markers_and_checklist(tmp_path):
    ws = _make_ws(tmp_path)
    script = _write_script(ws)

    out = vo_plan(workspace_path=str(ws), script_file=script, wpm=150)
    assert out["status"] == "success", out
    data = out["data"]

    assert data["cue_count"] == 3
    assert data["placement"] == "markers"
    assert all(c["est_seconds"] > 0 for c in data["cues"])
    # Cumulative, back-to-back timing.
    assert data["cues"][0]["start_seconds"] == 0.0
    assert data["cues"][1]["start_seconds"] == data["cues"][0]["end_seconds"]

    # Plan JSON + checklist written.
    assert Path(data["plan_path"]) == ws / "reports" / "vo_plan.json"
    checklist = Path(data["checklist_path"])
    assert checklist.exists()
    assert "cue_01" in checklist.read_text(encoding="utf-8")

    # Markers written, one per cue.
    marker_path = Path(data["marker_path"])
    assert marker_path == ws / "markers" / "vo_cues_markers.json"
    markers = json.loads(marker_path.read_text(encoding="utf-8"))
    assert len(markers) == 3


# ---------------------------------------------------------------------------
# vo_plan -> guides + vo_attach + vo_status
# ---------------------------------------------------------------------------

def test_vo_plan_guides_then_attach_and_status(tmp_path):
    ws = _make_ws(tmp_path)
    script = _write_script(ws)
    project = _write_project(ws)

    planned = vo_plan(
        workspace_path=str(ws), script_file=script, wpm=150, project_file=project
    )
    assert planned["status"] == "success", planned
    assert planned["data"]["placement"] == "guides"
    assert len(planned["data"]["guides"]) == 3

    # Guides landed in the project (one per cue).
    proj = parse_project(ws / project)
    assert len(proj.guides) == 3
    fps = proj.profile.fps  # 30

    # Record a take for cue_02, ~2.5s longer than its short estimate.
    cue2 = planned["data"]["cues"][1]
    take = ws / "media" / "raw" / "take_cue02.wav"
    take.parent.mkdir(parents=True, exist_ok=True)
    _render_sine_take(take, seconds=2.5)

    attached = vo_attach(
        workspace_path=str(ws),
        project_file=project,
        cue_id="cue_02",
        audio_file=str(take),
    )
    assert attached["status"] == "success", attached
    ad = attached["data"]
    assert ad["actual_seconds"] == pytest.approx(2.5, abs=0.15)
    assert "delta_seconds" in ad
    # Downstream drift reported for cue_03 (only later cues).
    assert [d["cue_id"] for d in ad["downstream_drift"]] == ["cue_03"]

    # The take is placed on the audio track at the cue's planned frame.
    proj2 = parse_project(ws / project)
    aps = audio_playlists(proj2)
    assert aps, "no audio playlist found after attach"
    entries = aps[0].entries
    real = [e for e in entries if e.producer_id]
    assert len(real) == 1
    expected_frame = int(round(cue2["start_seconds"] * fps))
    if expected_frame > 0:
        # A leading blank gap of exactly the cue's start position.
        gap = entries[0]
        assert gap.producer_id == ""
        assert gap.out_point == expected_frame - 1
    # Producer resource points at the recorded take.
    prod = next(p for p in proj2.producers if p.id == real[0].producer_id)
    assert prod.resource == str(take)

    # Status shows one recorded, two missing.
    status = vo_status(workspace_path=str(ws))
    assert status["status"] == "success", status
    sd = status["data"]
    assert sd["recorded"] == 1
    assert sd["missing"] == 2
    row2 = next(r for r in sd["rows"] if r["cue_id"] == "cue_02")
    assert row2["status"] == "recorded"
    assert row2["actual_seconds"] == ad["actual_seconds"]


def test_vo_attach_unknown_cue_errors(tmp_path):
    ws = _make_ws(tmp_path)
    script = _write_script(ws)
    project = _write_project(ws)
    vo_plan(workspace_path=str(ws), script_file=script, project_file=project)
    take = ws / "t.wav"
    _render_sine_take(take, 1.0)
    out = vo_attach(
        workspace_path=str(ws), project_file=project,
        cue_id="cue_99", audio_file=str(take),
    )
    assert out["status"] == "error"
