"""Integration tests for the ``effect_scifi_greenscreen`` MCP bundle tool.

Exercises the full tutorial keying recipe (Key Spill Mop Up -> advanced chroma
key -> Despill) through the real workspace + snapshot pipeline, in the style of
``tests/integration/test_stack_ops_mcp_tools.py``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools


def _callable(tool):
    """Return the plain callable for an MCP tool.

    Depending on the installed FastMCP version, ``@mcp.tool()`` either returns
    the original function (directly callable) or a ``FunctionTool`` wrapper that
    stores the function on ``.fn`` / ``.func`` / ``.__wrapped__``. This resolves
    whichever form is present so the tests exercise the real implementation.
    """
    if callable(tool) and type(tool).__name__ not in ("FunctionTool", "Tool"):
        return tool
    for attr in ("fn", "func", "__wrapped__"):
        inner = getattr(tool, attr, None)
        if callable(inner):
            return inner
    if callable(tool):
        return tool
    raise TypeError(f"cannot resolve callable for {tool!r}")


effect_scifi_greenscreen = _callable(tools.effect_scifi_greenscreen)
workspace_create = _callable(tools.workspace_create)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK = 2
CLIP = 0


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Scifi Greenscreen Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _services(ws: Path, pf: str) -> list[str]:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)
    return [e["mlt_service"] for e in patcher.list_effects(project, (TRACK, CLIP))]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tool_importable_and_callable():
    assert hasattr(tools, "effect_scifi_greenscreen")
    assert callable(effect_scifi_greenscreen)


# ---------------------------------------------------------------------------
# Happy path -- full three-effect recipe, in order
# ---------------------------------------------------------------------------


def test_full_recipe_inserts_three_filters_in_order(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["filter_count"] == 3
    assert data["screen_type"] == "green"
    assert data["services"] == [
        "frei0r.keyspillm0pup",
        "avfilter.hsvkey",
        "avfilter.despill",
    ]
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    # The recipe is appended after any pre-existing filters, in the tutorial's
    # load-bearing order (spill correction FIRST, key SECOND, despill LAST).
    fei = data["first_effect_index"]
    assert _services(ws, pf)[fei:] == [
        "frei0r.keyspillm0pup",
        "avfilter.hsvkey",
        "avfilter.despill",
    ]


def test_snapshot_dir_created(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    snap = out["data"]["snapshot_id"]
    assert (ws / "projects" / "snapshots" / snap).is_dir()


def test_appends_after_existing_filters(tmp_path):
    ws, pf = _make_ws(tmp_path)
    first = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        despill=False, spill_correction=False,  # just the key
    )
    assert first["status"] == "success", first
    assert first["data"]["filter_count"] == 1
    base = first["data"]["first_effect_index"]

    second = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert second["status"] == "success", second
    # The second call appends after the pre-existing filters + the first key.
    assert second["data"]["first_effect_index"] == base + 1
    services = _services(ws, pf)
    assert services[base:] == [
        "avfilter.hsvkey",              # from the first call
        "frei0r.keyspillm0pup",         # second call, in order
        "avfilter.hsvkey",
        "avfilter.despill",
    ]


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------


def test_spill_correction_off_omits_keyspill(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        spill_correction=False,
    )
    assert out["status"] == "success", out
    assert out["data"]["services"] == ["avfilter.hsvkey", "avfilter.despill"]
    fei = out["data"]["first_effect_index"]
    assert _services(ws, pf)[fei:] == ["avfilter.hsvkey", "avfilter.despill"]


def test_despill_off_omits_despill(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        despill=False,
    )
    assert out["status"] == "success", out
    assert out["data"]["services"] == ["frei0r.keyspillm0pup", "avfilter.hsvkey"]


def test_blue_screen_type(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        key_color="#0000FF",
    )
    assert out["status"] == "success", out
    assert out["data"]["screen_type"] == "blue"


def test_key_color_drives_hsvkey_property(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        key_color="#00FF00",
    )
    assert out["status"] == "success", out
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)
    # hsvkey sits just after the keyspill filter; hue of pure green is ~120 deg.
    hsvkey_idx = out["data"]["first_effect_index"] + 1
    hue = patcher.get_effect_property(project, (TRACK, CLIP), hsvkey_idx, "av.hue")
    assert hue is not None
    assert abs(float(hue) - 120.0) < 1.0


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file="nope.kdenlive", track=TRACK, clip=CLIP,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_bad_color(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        key_color="chartreuse",
    )
    assert out["status"] == "error"


def test_tolerance_far_less_than_near(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        tolerance_near=0.5, tolerance_far=0.1,
    )
    assert out["status"] == "error"
    assert "tolerance_far" in out["message"]


def test_bad_clip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=99,
    )
    assert out["status"] == "error"


def test_out_of_range_despill_amount(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_scifi_greenscreen(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        despill_amount=5.0,
    )
    assert out["status"] == "error"
