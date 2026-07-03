"""Integration tests for the ``title_card_add`` bundle MCP tool.

Style mirrors ``tests/integration/test_stack_ops_mcp_tools.py``: build a project
fixture, drive the tool, reparse and assert against the resulting model.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server.bundles.titles import title_card_add

# Under the fastmcp version used here, ``@mcp.tool()`` yields a FunctionTool
# wrapper; ``.fn`` is the underlying plain function (falls back to the object
# itself when the decorator returns the function directly).
_add = getattr(title_card_add, "fn", title_card_add)


def _make_project(tmp_path: Path, w: int = 1920, h: int = 1080, fps: float = 25.0) -> Path:
    proj = KdenliveProject(
        version="7",
        title="TitleTest",
        profile=ProjectProfile(width=w, height=h, fps=fps),
        producers=[
            Producer(
                id="bg",
                resource="0x004488ff",
                properties={"mlt_service": "color", "resource": "0x004488ff", "length": "300"},
            )
        ],
        tracks=[Track(id="v1", track_type="video")],
        playlists=[
            Playlist(id="v1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=299)])
        ],
    )
    path = tmp_path / "base.kdenlive"
    serialize_project(project=proj, output_path=path)
    return path


def _title_producers(project: KdenliveProject) -> list[Producer]:
    return [p for p in project.producers if p.properties.get("mlt_service") == "kdenlivetitle"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tool_registered_with_server():
    import asyncio

    from workshop_video_brain.server import mcp

    tool = asyncio.run(mcp.get_tool("title_card_add"))
    assert tool is not None
    assert tool.name == "title_card_add"


def test_tool_callable():
    assert callable(_add)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_adds_title_producer_on_new_top_track(tmp_path):
    proj = _make_project(tmp_path)
    n_tracks = len(parse_project(proj).tracks)

    out = _add(
        project_file=str(proj),
        text="Jane Doe",
        subtitle="Host",
        style="lower-third",
        at_seconds=2.0,
        duration_seconds=3.0,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["new_track"] is True
    assert data["duration_frames"] == 75  # 3s * 25fps
    assert data["at_frame"] == 50  # 2s * 25fps

    project = parse_project(proj)
    titles = _title_producers(project)
    assert len(titles) == 1
    # xmldata is a valid kdenlivetitle document carrying the text
    xml = titles[0].properties["xmldata"]
    root = ET.fromstring(xml)
    assert root.tag == "kdenlivetitle"
    assert "Jane Doe" in xml and "Host" in xml
    # a new top video track was appended
    assert len(project.tracks) == n_tracks + 1


def test_placed_at_correct_frame_with_blank_pad(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(
        project_file=str(proj), text="Later", at_seconds=4.0, duration_seconds=1.0
    )
    assert out["status"] == "success", out

    project = parse_project(proj)
    track_id = out["data"]["track_id"]
    playlist = next(p for p in project.playlists if p.id == track_id)
    # a blank gap precedes the title entry (100 frames == 4s @ 25fps)
    assert playlist.entries[0].producer_id == ""
    title_entry = playlist.entries[-1]
    assert title_entry.producer_id == out["data"]["producer_id"]
    assert title_entry.out_point == 24  # 1s @ 25fps -> frames 0..24


def test_explicit_track_index(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(
        project_file=str(proj), text="OnV1", at_seconds=0.0, duration_seconds=1.0, track=0
    )
    assert out["status"] == "success", out
    assert out["data"]["new_track"] is False
    assert out["data"]["track"] == 0


def test_chapter_card_style(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(
        project_file=str(proj), text="Chapter One", style="chapter-card",
        at_seconds=0.0, duration_seconds=2.0,
    )
    assert out["status"] == "success", out
    project = parse_project(proj)
    xml = _title_producers(project)[0].properties["xmldata"]
    root = ET.fromstring(xml)
    # chapter-card centres the text (Qt::AlignHCenter == 4)
    title = root.findall("item[@type='QGraphicsTextItem']")[0]
    assert title.find("content").get("alignment") == "4"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_project(tmp_path):
    out = _add(project_file=str(tmp_path / "nope.kdenlive"), text="X")
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_unknown_style(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(project_file=str(proj), text="X", style="does-not-exist")
    assert out["status"] == "error"
    assert "does-not-exist" in out["message"]


def test_empty_text_rejected(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(project_file=str(proj), text="   ")
    assert out["status"] == "error"


def test_out_of_range_track(tmp_path):
    proj = _make_project(tmp_path)
    out = _add(project_file=str(proj), text="X", track=99)
    assert out["status"] == "error"
