"""Integration tests for the guide + chapter MCP tools.

Exercises guide_add / guide_list / guide_remove / publish_chapters against a
real fixture project inside a real workspace (snapshot pipeline included),
mirroring the style of test_mcp_tools.py / test_masking_mcp_tools.py.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

# Import server so all @mcp.tool() bundles (incl. guides) are registered.
import workshop_video_brain.server as _server  # noqa: F401
from workshop_video_brain.edit_mcp.server.bundles import guides as _bundle
import workshop_video_brain.edit_mcp.server.tools as _tools


def _fn(tool):
    """Return the plain callable behind a possibly-wrapped MCP tool.

    Depending on the installed fastmcp version ``@mcp.tool()`` returns the
    original function or a ``FunctionTool`` wrapper (callable on ``.fn``).
    """
    return getattr(tool, "fn", tool)


guide_add = _fn(_bundle.guide_add)
guide_list = _fn(_bundle.guide_list)
guide_remove = _fn(_bundle.guide_remove)
publish_chapters = _fn(_bundle.publish_chapters)
workspace_create = _fn(_tools.workspace_create)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"


def _make_ws(tmp_path: Path, project_name: str = "guides_test.kdenlive") -> tuple[Path, Path]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Guides Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, dest


def _write_markers(ws_root: Path, items: list[dict]) -> None:
    markers_dir = ws_root / "markers"
    markers_dir.mkdir(parents=True, exist_ok=True)
    (markers_dir / "clip_markers.json").write_text(
        json.dumps(items), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_tools_registered():
    lister = getattr(_server.mcp, "list_tools", None) or _server.mcp.get_tools
    result = asyncio.run(lister())
    if isinstance(result, dict):
        names = set(result.keys())
    else:
        names = {getattr(t, "name", t) for t in result}
    for name in ("guide_add", "guide_list", "guide_remove", "publish_chapters"):
        assert name in names, f"{name} not registered"


# ---------------------------------------------------------------------------
# guide_add / guide_list / guide_remove
# ---------------------------------------------------------------------------

def test_guide_add_and_list(tmp_path):
    ws, proj = _make_ws(tmp_path)

    out = guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    assert out["status"] == "success", out
    assert out["data"]["guide_count"] == 1
    assert out["data"]["snapshot_id"]  # snapshot taken inside workspace

    out2 = guide_add(project_file=str(proj), at_seconds=5.0, label="Chapter One",
                     category="2")
    assert out2["status"] == "success"
    assert out2["data"]["guide_count"] == 2

    listed = guide_list(project_file=str(proj))
    assert listed["status"] == "success"
    rows = listed["data"]["guides"]
    assert [r["label"] for r in rows] == ["Intro", "Chapter One"]
    # fixture is 30fps -> 5s == frame 150
    assert rows[1]["position_frames"] == 150
    assert rows[1]["timecode"] == "00:05"

    # docproperties JSON is real Kdenlive format
    doc = json.loads(listed["data"]["docproperties_guides_json"])
    assert doc[0] == {"pos": 0, "comment": "Intro", "type": 0}
    assert doc[1]["type"] == 2


def test_guide_remove_by_label(tmp_path):
    ws, proj = _make_ws(tmp_path)
    guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    guide_add(project_file=str(proj), at_seconds=10.0, label="Outro")

    out = guide_remove(project_file=str(proj), at_seconds_or_label="Outro")
    assert out["status"] == "success", out
    assert out["data"]["removed_count"] == 1
    assert out["data"]["guide_count"] == 1
    assert out["data"]["guides"][0]["label"] == "Intro"


def test_guide_remove_by_seconds(tmp_path):
    ws, proj = _make_ws(tmp_path)
    guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    guide_add(project_file=str(proj), at_seconds=4.0, label="Mid")

    out = guide_remove(project_file=str(proj), at_seconds_or_label="4.0")
    assert out["status"] == "success", out
    assert out["data"]["removed_count"] == 1
    assert out["data"]["guides"][0]["label"] == "Intro"


def test_guide_remove_no_match_errors(tmp_path):
    ws, proj = _make_ws(tmp_path)
    guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    out = guide_remove(project_file=str(proj), at_seconds_or_label="Nope")
    assert out["status"] == "error"


def test_guide_add_missing_file():
    out = guide_add(project_file="/nonexistent/x.kdenlive", at_seconds=0.0,
                    label="X")
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# publish_chapters
# ---------------------------------------------------------------------------

def test_publish_chapters_from_guides(tmp_path):
    ws, proj = _make_ws(tmp_path)
    guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    guide_add(project_file=str(proj), at_seconds=30.0, label="Setup")
    guide_add(project_file=str(proj), at_seconds=60.0, label="Wrap Up")

    out = publish_chapters(project_file_or_workspace=str(proj))
    assert out["status"] == "success", out
    text = out["data"]["chapters_text"]
    assert text.startswith("00:00 Intro")
    assert "00:30 Setup" in text
    assert "01:00 Wrap Up" in text
    assert out["data"]["warnings"] == []  # valid: 3 chapters, all >=10s apart

    # File written to reports/chapters.txt in the workspace
    written = Path(out["data"]["path"])
    assert written == ws / "reports" / "chapters.txt"
    assert written.read_text(encoding="utf-8") == text


def test_publish_chapters_min_gap_merge(tmp_path):
    ws, proj = _make_ws(tmp_path)
    guide_add(project_file=str(proj), at_seconds=0.0, label="Intro")
    guide_add(project_file=str(proj), at_seconds=3.0, label="TooClose")
    guide_add(project_file=str(proj), at_seconds=30.0, label="Real")

    out = publish_chapters(project_file_or_workspace=str(proj), min_gap_seconds=10.0)
    assert out["status"] == "success"
    text = out["data"]["chapters_text"]
    assert "TooClose" not in text  # dropped by min-gap merge
    assert out["data"]["count"] == 2


def test_publish_chapters_inserts_zero_and_warns(tmp_path):
    ws, proj = _make_ws(tmp_path)
    # Only one guide, not at zero -> Intro inserted, <3 chapters -> warning
    guide_add(project_file=str(proj), at_seconds=45.0, label="Later")

    out = publish_chapters(project_file_or_workspace=str(proj))
    assert out["status"] == "success"
    assert out["data"]["chapters_text"].startswith("00:00 Intro")
    assert any("three" in w for w in out["data"]["warnings"])


def test_publish_chapters_from_workspace_markers(tmp_path):
    ws, proj = _make_ws(tmp_path)
    _write_markers(ws, [
        {"start_seconds": 0.0, "category": "chapter_candidate",
         "suggested_label": "Welcome", "reason": ""},
        {"start_seconds": 40.0, "category": "chapter_candidate",
         "suggested_label": "Deep Dive", "reason": ""},
    ])
    # Point at the workspace directory (no project guides).
    out = publish_chapters(project_file_or_workspace=str(ws))
    assert out["status"] == "success", out
    text = out["data"]["chapters_text"]
    assert "00:00 Welcome" in text
    assert "00:40 Deep Dive" in text
