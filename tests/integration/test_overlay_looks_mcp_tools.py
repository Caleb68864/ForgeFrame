"""Integration tests for the additive-overlay bundle tools.

``effect_light_leak`` + ``effect_day_to_night`` (bundle module
``server/bundles/overlay_looks.py``). Mirrors the style of
``test_composite_set_mcp_tool.py``: workspace boundary, snapshot capture,
serializer round-trip, bundle registration via ``list_tools``, and the error
contract.

The fixture ``keyframe_project.kdenlive`` exposes three video tracks
(playlist0/1/2); the only real clip lives on video track 2, clip 0.
"""
from __future__ import annotations

import asyncio
import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

# Importing tools registers the core surface; importing the bundles package
# triggers the auto-importer that registers overlay_looks.
from workshop_video_brain.edit_mcp.server import tools as _tools_mod  # noqa: F401
import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles import overlay_looks as _ol_mod


def _callable(mod, name: str):
    """Return the underlying function for an MCP tool.

    Depending on the installed fastmcp version, ``@mcp.tool()`` may return the
    original function or wrap it in a ``FunctionTool`` (callable via ``.fn``).
    Unwrap so the test drives the real implementation (mirrors the hologram test).
    """
    obj = getattr(mod, name)
    return getattr(obj, "fn", obj)


workspace_create = _callable(_tools_mod, "workspace_create")
effect_light_leak = _callable(_ol_mod, "effect_light_leak")
effect_day_to_night = _callable(_ol_mod, "effect_day_to_night")

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

CLIP_TRACK = 2   # the fixture's only real clip
CLIP_INDEX = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str, Path]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Overlay Looks Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    shutil.copy(FIXTURE, ws_root / project_name)
    return ws_root, project_name, media_root


def _media(media_root: Path, name: str) -> str:
    f = media_root / name
    f.write_bytes(b"\x00")
    return str(f)


def _elements(project_path: Path, tag: str) -> list[ET.Element]:
    return list(ET.fromstring(project_path.read_text(encoding="utf-8")).iter(tag))


def _services(project_path: Path, tag: str) -> list[str]:
    return [e.attrib.get("mlt_service") for e in _elements(project_path, tag)]


# ---------------------------------------------------------------------------
# Registration / signatures
# ---------------------------------------------------------------------------

def _registered_tool_names() -> set[str]:
    """Tool names known to the FastMCP singleton, across fastmcp versions."""
    getter = getattr(mcp, "get_tools", None) or getattr(mcp, "list_tools")
    res = getter()
    if inspect.isawaitable(res):
        res = asyncio.run(res)
    if isinstance(res, dict):
        return set(res.keys())
    return {getattr(t, "name", t) for t in res}


def test_bundle_tools_registered_via_list_tools():
    names = _registered_tool_names()
    assert "effect_light_leak" in names
    assert "effect_day_to_night" in names


def test_light_leak_signature():
    params = list(inspect.signature(effect_light_leak).parameters)
    assert params == [
        "workspace_path", "project_file", "leak_media", "target_track",
        "at_frame", "overlay_track", "blend_mode", "opacity",
        "fade_in_frames", "fade_out_frames", "duration_frames",
    ]


def test_day_to_night_signature():
    params = list(inspect.signature(effect_day_to_night).parameters)
    assert params == [
        "workspace_path", "project_file", "track", "clip_index",
        "intensity", "sky_media", "keyframed", "blend_mode",
        "overlay_track", "sky_at_frame", "sky_duration_frames",
    ]


# ---------------------------------------------------------------------------
# effect_light_leak — success paths
# ---------------------------------------------------------------------------

def test_light_leak_screen_writes_overlay_and_composite(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=30, overlay_track=1,
        blend_mode="screen", opacity=0.8, duration_frames=120,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["overlay_track"] == 1
    assert data["blend_mode"] == "screen"
    assert data["composition_added"] is True
    assert data["end_frame"] == 149
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    proj = ws / pf
    # A cairoblend (screen) transition was written.
    cairo = [t for t in _elements(proj, "transition")
             if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    assert cairo, "no frei0r.cairoblend transition"
    props = {p.attrib["name"]: (p.text or "") for p in cairo[-1].findall("property")}
    assert props["1"] == "screen"
    assert props["geometry"].endswith(":80")  # opacity 0.8 -> 80
    # The leak producer + entry landed on the overlay track.
    assert any(p.attrib.get("id", "").startswith("leak_")
               for p in _elements(proj, "producer"))


def test_light_leak_lighten_mode(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, overlay_track=1,
        blend_mode="lighten", duration_frames=60,
    )
    assert out["status"] == "success", out
    cairo = [t for t in _elements(ws / pf, "transition")
             if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    props = {p.attrib["name"]: (p.text or "") for p in cairo[-1].findall("property")}
    assert props["1"] == "lighten"


def test_light_leak_fade_writes_affine_filter(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    before = _services(ws / pf, "filter").count("affine")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, overlay_track=1,
        fade_in_frames=10, fade_out_frames=10, duration_frames=120,
    )
    assert out["status"] == "success", out
    assert out["data"]["fade_effect_index"] == 0
    after = _services(ws / pf, "filter").count("affine")
    assert after == before + 1  # one new fade transform


def test_light_leak_default_overlay_track_is_target_plus_one(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, duration_frames=60,
    )
    assert out["status"] == "success", out
    assert out["data"]["overlay_track"] == 1


def test_light_leak_creates_snapshot_on_disk(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, overlay_track=1, duration_frames=60,
    )
    assert out["status"] == "success", out
    snap_dir = ws / "projects" / "snapshots" / out["data"]["snapshot_id"]
    assert snap_dir.is_dir()


# ---------------------------------------------------------------------------
# effect_light_leak — error paths
# ---------------------------------------------------------------------------

def test_light_leak_unknown_blend_mode(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, overlay_track=1,
        blend_mode="multiply", duration_frames=60,
    )
    assert out["status"] == "error"
    assert "multiply" in out["message"]


def test_light_leak_missing_leak_media(tmp_path):
    ws, pf, _media_root = _make_ws(tmp_path)
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf,
        leak_media=str(ws / "nope.mp4"),
        target_track=0, at_frame=0, overlay_track=1, duration_frames=60,
    )
    assert out["status"] == "error"
    assert "nope.mp4" in out["message"]


def test_light_leak_missing_project(tmp_path):
    ws, _pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file="missing.kdenlive", leak_media=leak,
        target_track=0, at_frame=0, overlay_track=1, duration_frames=60,
    )
    assert out["status"] == "error"
    assert "missing.kdenlive" in out["message"]


def test_light_leak_same_track_rejected(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=1, at_frame=0, overlay_track=1, duration_frames=60,
    )
    assert out["status"] == "error"
    assert "track" in out["message"].lower()


def test_light_leak_overlay_track_out_of_range(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    leak = _media(media, "leak.mp4")
    out = effect_light_leak(
        workspace_path=str(ws), project_file=pf, leak_media=leak,
        target_track=0, at_frame=0, overlay_track=9, duration_frames=60,
    )
    assert out["status"] == "error"
    assert "out of range" in out["message"]


# ---------------------------------------------------------------------------
# effect_day_to_night — success paths
# ---------------------------------------------------------------------------

def test_day_to_night_keyframed_writes_eq_and_colorize(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX, intensity=0.6, keyframed=True,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["services"] == ["avfilter.eq", "frei0r.colorize"]
    assert data["filter_count"] == 2
    assert data["keyframed"] is True
    assert data["sky"] is None

    filters = _services(ws / pf, "filter")
    assert "avfilter.eq" in filters
    assert "frei0r.colorize" in filters
    # eq brightness is a keyframe ramp (contains ';' and '=').
    eq = [f for f in _elements(ws / pf, "filter")
          if f.attrib.get("mlt_service") == "avfilter.eq"][-1]
    props = {p.attrib["name"]: (p.text or "") for p in eq.findall("property")}
    assert ";" in props["av.brightness"] and "=" in props["av.brightness"]


def test_day_to_night_static_when_not_keyframed(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX, intensity=0.5, keyframed=False,
    )
    assert out["status"] == "success", out
    eq = [f for f in _elements(ws / pf, "filter")
          if f.attrib.get("mlt_service") == "avfilter.eq"][-1]
    props = {p.attrib["name"]: (p.text or "") for p in eq.findall("property")}
    assert ";" not in props["av.brightness"]
    assert "=" not in props["av.brightness"]


def test_day_to_night_with_sky_overlay(tmp_path):
    ws, pf, media = _make_ws(tmp_path)
    sky = _media(media, "sky.mp4")
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX, intensity=0.5,
        sky_media=sky, blend_mode="lighten", overlay_track=1,
        sky_duration_frames=90,
    )
    assert out["status"] == "success", out
    assert out["data"]["sky"] is not None
    assert out["data"]["sky"]["blend_mode"] == "lighten"
    # sky producer + a cairoblend (lighten) transition present
    assert any(p.attrib.get("id", "").startswith("sky_")
               for p in _elements(ws / pf, "producer"))
    cairo = [t for t in _elements(ws / pf, "transition")
             if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    assert cairo
    props = {p.attrib["name"]: (p.text or "") for p in cairo[-1].findall("property")}
    assert props["1"] == "lighten"


def test_day_to_night_creates_snapshot(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
    )
    assert out["status"] == "success", out
    snap_dir = ws / "projects" / "snapshots" / out["data"]["snapshot_id"]
    assert snap_dir.is_dir()


# ---------------------------------------------------------------------------
# effect_day_to_night — error paths
# ---------------------------------------------------------------------------

def test_day_to_night_bad_intensity(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX, intensity=2.0,
    )
    assert out["status"] == "error"
    assert "intensity" in out["message"]


def test_day_to_night_bad_clip_index(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=9,
    )
    assert out["status"] == "error"
    assert "out of range" in out["message"]


def test_day_to_night_missing_sky_media(tmp_path):
    ws, pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        sky_media=str(ws / "nope-sky.mp4"), overlay_track=1,
    )
    assert out["status"] == "error"
    assert "nope-sky.mp4" in out["message"]


def test_day_to_night_missing_project(tmp_path):
    ws, _pf, _media = _make_ws(tmp_path)
    out = effect_day_to_night(
        workspace_path=str(ws), project_file="missing.kdenlive",
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
    )
    assert out["status"] == "error"
    assert "missing.kdenlive" in out["message"]
