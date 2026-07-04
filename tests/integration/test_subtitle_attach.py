"""Integration tests for the real subtitle-track MCP tools.

Exercises ``subtitles_attach`` end-to-end against a real fixture project inside a
real workspace (snapshot + parser/serializer round-trip), plus registration
asserts.  Render/burn-in proofs live in the external oracle suite.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

import workshop_video_brain.server as _server  # noqa: F401
from workshop_video_brain.edit_mcp.server.bundles import subtitle_track as _bundle
import workshop_video_brain.edit_mcp.server.tools as _tools
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project


from tests._testkit import unwrap as _fn  # noqa: E402


subtitles_attach = _fn(_bundle.subtitles_attach)
subtitles_burn_in = _fn(_bundle.subtitles_burn_in)
workspace_create = _fn(_tools.workspace_create)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\nSecond caption\n"
)


def _make_ws(tmp_path: Path) -> tuple[Path, Path]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Subs Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / "subs_test.kdenlive"
    shutil.copy(FIXTURE, dest)
    return ws_root, dest


def _write_srt(ws_root: Path, name: str = "captions.srt") -> Path:
    reports = ws_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    p = reports / name
    p.write_text(SRT, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_tools_registered():
    lister = getattr(_server.mcp, "list_tools", None) or _server.mcp.get_tools
    result = asyncio.run(lister())
    names = set(result.keys()) if isinstance(result, dict) else {
        getattr(t, "name", t) for t in result
    }
    for name in ("subtitles_attach", "subtitles_burn_in"):
        assert name in names, f"{name} not registered"


# ---------------------------------------------------------------------------
# subtitles_attach
# ---------------------------------------------------------------------------

def test_attach_default_latest_srt(tmp_path):
    ws, proj = _make_ws(tmp_path)
    _write_srt(ws)

    out = subtitles_attach(workspace_path=str(ws), project_file=str(proj))
    assert out["status"] == "success", out
    data = out["data"]
    assert data["cue_count"] == 2
    assert data["subtitle_track_count"] == 1
    assert data["snapshot_id"]

    # Sidecar .ass written next to the project, Kdenlive {project}.ass pattern.
    sidecar = Path(data["sidecar_path"])
    assert sidecar.exists()
    assert sidecar.name == "subs_test.kdenlive.ass"
    assert "[V4+ Styles]" in sidecar.read_text(encoding="utf-8")

    # subtitlesList docproperties assembled correctly.
    lst = json.loads(data["subtitles_list_json"])
    assert lst == [{"name": "captions", "id": 0, "file": "subs_test.kdenlive.ass"}]


def test_attach_writes_avfilter_and_docproperties(tmp_path):
    ws, proj = _make_ws(tmp_path)
    _write_srt(ws)
    subtitles_attach(workspace_path=str(ws), project_file=str(proj))

    xml = proj.read_text(encoding="utf-8")
    assert "avfilter.subtitles" in xml
    assert 'name="kdenlive:docproperties.subtitlesList"' in xml
    assert 'name="kdenlive:docproperties.activeSubtitleIndex"' in xml
    assert 'name="kdenlive:sequenceproperties.subtitlesList"' in xml

    # And it round-trips back through the parser.
    reparsed = parse_project(proj)
    assert len(reparsed.subtitles) == 1
    assert reparsed.subtitles[0].file.endswith("subs_test.kdenlive.ass")

    # The avfilter.subtitles filter is nested in the sequence tractor (the
    # producer_type=17 tractor -- where MLT renders subtitle pixels in the
    # modern E-shape document).
    root = ET.fromstring(xml)

    def _props(el):
        return {
            c.get("name"): (c.text or "")
            for c in el if c.tag == "property"
        }

    seq = next(
        t for t in root.findall("tractor")
        if _props(t).get("kdenlive:producer_type") == "17"
    )
    services = [
        pr.text for f in seq.findall("filter")
        for pr in f.findall("property") if pr.get("name") == "mlt_service"
    ]
    assert "avfilter.subtitles" in services


def test_attach_with_style_bakes_color(tmp_path):
    ws, proj = _make_ws(tmp_path)
    _write_srt(ws)
    out = subtitles_attach(
        workspace_path=str(ws), project_file=str(proj),
        style={"size": 64, "primary_color": "#FFFF00", "position": "top"},
    )
    assert out["status"] == "success", out
    assert out["data"]["styled"] is True
    ass = Path(out["data"]["sidecar_path"]).read_text(encoding="utf-8")
    assert "DejaVu Sans,64,&H0000FFFF" in ass   # yellow, size 64
    # alignment 8 (top-centre) is the second-to-... fields before margins
    style_line = [l for l in ass.splitlines() if l.startswith("Style: Default")][0]
    assert style_line.split(",")[18] == "8"


def test_attach_explicit_srt_path(tmp_path):
    ws, proj = _make_ws(tmp_path)
    srt = tmp_path / "external.srt"
    srt.write_text(SRT, encoding="utf-8")
    out = subtitles_attach(
        workspace_path=str(ws), project_file=str(proj), srt_path=str(srt)
    )
    assert out["status"] == "success", out
    assert out["data"]["srt_path"] == str(srt)


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------

def test_attach_no_srt_available_errors(tmp_path):
    ws, proj = _make_ws(tmp_path)  # no reports/*.srt written
    out = subtitles_attach(workspace_path=str(ws), project_file=str(proj))
    assert out["status"] == "error"
    assert "srt" in out["message"].lower()


def test_attach_missing_project_errors(tmp_path):
    ws, _ = _make_ws(tmp_path)
    _write_srt(ws)
    out = subtitles_attach(
        workspace_path=str(ws), project_file=str(ws / "nope.kdenlive")
    )
    assert out["status"] == "error"


def test_attach_bad_workspace_errors():
    out = subtitles_attach(workspace_path="", project_file="x")
    assert out["status"] == "error"


def test_resolve_project_picks_highest_version_not_lexicographic(tmp_path):
    """Regression: empty project_file must fall back to the numerically-latest
    working copy (``_v10`` > ``_v2``), not the lexicographic ``files[-1]`` which
    wrongly selected ``_v2``."""
    ws, _ = _make_ws(tmp_path)
    working = ws / "projects" / "working_copies"
    working.mkdir(parents=True, exist_ok=True)
    for ver in (2, 10):
        shutil.copy(FIXTURE, working / f"subs_test_v{ver}.kdenlive")
    resolved = _bundle._resolve_project(str(ws), "")
    assert resolved.name == "subs_test_v10.kdenlive", resolved
