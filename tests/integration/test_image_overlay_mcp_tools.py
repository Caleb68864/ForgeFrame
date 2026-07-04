"""Integration tests for the image-overlay bundle tools.

``overlay_insert`` + ``watermark_apply`` (bundle module
``server/bundles/image_overlay.py``).  Mirrors the style of
``test_overlay_looks_mcp_tools.py`` / ``test_title_card_mcp_tool.py``: real
workspace boundary, serializer round-trip, bundle registration, ``.fn`` unwrap,
and the error contract.
"""
from __future__ import annotations

import asyncio
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
from workshop_video_brain.edit_mcp.server import tools as _tools_mod  # noqa: F401
import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401  (auto-registers)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles import image_overlay as _io_mod


def _callable(mod, name: str):
    obj = getattr(mod, name)
    return getattr(obj, "fn", obj)


workspace_create = _callable(_tools_mod, "workspace_create")
overlay_insert = _callable(_io_mod, "overlay_insert")
watermark_apply = _callable(_io_mod, "watermark_apply")


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Image Overlay Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])

    proj = KdenliveProject(
        version="7",
        title="io",
        profile=ProjectProfile(width=320, height=180, fps=25.0),
        producers=[Producer(id="bg", resource="0x0000ffff",
                            properties={"mlt_service": "color", "resource": "0x0000ffff", "length": "300"})],
        tracks=[Track(id="v1", track_type="video"), Track(id="a1", track_type="audio")],
        playlists=[
            Playlist(id="v1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=99)]),
            Playlist(id="a1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=99)]),
        ],
    )
    serialize_project(project=proj, output_path=ws_root / project_name)
    return ws_root, project_name


def _png(ws: Path, name: str = "logo.png") -> str:
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGBA", (100, 60), (255, 0, 0, 255))
    p = ws / name
    img.save(p)
    return str(p)


def _svg(ws: Path, name: str = "logo.svg") -> str:
    p = ws / name
    p.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
        'width="100" height="100"><circle cx="50" cy="50" r="40" fill="#0f0"/></svg>'
    )
    return str(p)


def _image_producers(project: KdenliveProject) -> list[Producer]:
    return [p for p in project.producers if p.properties.get("mlt_service") == "qimage"]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_tools_registered_with_server():
    for name in ("overlay_insert", "watermark_apply"):
        tool = asyncio.run(mcp.get_tool(name))
        assert tool is not None and tool.name == name


def test_tools_callable():
    assert callable(overlay_insert) and callable(watermark_apply)


# ---------------------------------------------------------------------------
# overlay_insert happy paths
# ---------------------------------------------------------------------------

def test_overlay_insert_new_top_track(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    n_tracks = len(parse_project(ws / proj_name).tracks)

    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        at_seconds=1.0, duration_seconds=2.0, rect="bottom_right", opacity=0.8,
    )
    assert out["status"] == "success", out
    d = out["data"]
    assert d["new_track"] is True
    assert d["producer_service"] == "qimage"
    assert d["at_frame"] == 25       # 1s @ 25fps
    assert d["duration_frames"] == 50  # 2s @ 25fps
    assert d["rect"] is not None
    assert d["transform_added"] is True

    project = parse_project(ws / proj_name)
    imgs = _image_producers(project)
    assert len(imgs) == 1
    assert len(project.tracks) == n_tracks + 1


def test_overlay_insert_blank_pad_and_entry(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        at_seconds=2.0, duration_seconds=1.0,
    )
    assert out["status"] == "success", out
    project = parse_project(ws / proj_name)
    track_id = out["data"]["track_id"]
    playlist = next(p for p in project.playlists if p.id == track_id)
    assert playlist.entries[0].producer_id == ""       # blank pad (50 frames)
    last = playlist.entries[-1]
    assert last.producer_id == out["data"]["producer_id"]
    assert last.out_point == 24                          # 1s -> frames 0..24


def test_overlay_insert_filter_nested_in_entry(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        at_seconds=0.0, duration_seconds=1.0, rect="center",
    )
    assert out["status"] == "success", out
    # §1.1: the qtblend transform must be nested inside the clip <entry>.
    root = ET.parse(ws / proj_name).getroot()
    nested = root.findall(".//playlist/entry/filter")
    services = [f.find("property").text for f in nested]
    assert "qtblend" in services


def test_overlay_insert_explicit_track(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        at_seconds=0.0, duration_seconds=1.0, track=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["new_track"] is False
    assert out["data"]["track"] == 0


def test_overlay_insert_svg_accepted(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    svg = _svg(ws)
    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=svg,
        at_seconds=0.0, duration_seconds=1.0,
    )
    assert out["status"] == "success", out
    assert out["data"]["is_svg"] is True


def test_overlay_insert_fades(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        at_seconds=0.0, duration_seconds=2.0, fade_in_frames=10, fade_out_frames=10,
    )
    assert out["status"] == "success", out
    root = ET.parse(ws / proj_name).getroot()
    rects = [
        p.text for f in root.findall(".//playlist/entry/filter")
        for p in f.findall("property") if p.get("name") == "rect"
    ]
    assert rects and ";" in rects[0]  # keyframed opacity ramp


# ---------------------------------------------------------------------------
# watermark_apply
# ---------------------------------------------------------------------------

def test_watermark_apply_full_duration_corner(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = watermark_apply(
        workspace_path=str(ws), project_file=proj_name, image_path=png,
        position="bottom_right", scale=0.15, opacity=0.6,
    )
    assert out["status"] == "success", out
    d = out["data"]
    assert d["duration_frames"] == 100   # spans the base track
    assert d["position"] == "bottom_right"
    # placed toward the bottom-right of the 320x180 frame
    x, y, w, h = d["rect"]
    assert x > 160 and y > 90


def test_watermark_rejects_full_position(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = watermark_apply(
        workspace_path=str(ws), project_file=proj_name, image_path=png, position="full",
    )
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------

def test_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(workspace_path=str(ws), project_file="nope.kdenlive",
                         image_path=png, at_seconds=0.0)
    assert out["status"] == "error" and "nope.kdenlive" in out["message"]


def test_missing_image(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    out = overlay_insert(workspace_path=str(ws), project_file=proj_name,
                         image_path=str(ws / "ghost.png"), at_seconds=0.0)
    assert out["status"] == "error" and "does not exist" in out["message"]


def test_unsupported_image_type(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    bad = ws / "clip.mp4"
    bad.write_bytes(b"\x00")
    out = overlay_insert(workspace_path=str(ws), project_file=proj_name,
                         image_path=str(bad), at_seconds=0.0)
    assert out["status"] == "error" and "unsupported" in out["message"]


def test_bad_opacity(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(workspace_path=str(ws), project_file=proj_name,
                         image_path=png, at_seconds=0.0, opacity=1.5)
    assert out["status"] == "error"


def test_out_of_range_track(tmp_path):
    ws, proj_name = _make_ws(tmp_path)
    png = _png(ws)
    out = overlay_insert(workspace_path=str(ws), project_file=proj_name,
                         image_path=png, at_seconds=0.0, track=99)
    assert out["status"] == "error"
