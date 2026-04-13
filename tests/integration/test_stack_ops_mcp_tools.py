"""Integration tests for Stack-Ops MCP tools.

Covers ``effects_copy``, ``effects_paste``, and ``effect_reorder``, registered
in ``workshop_video_brain.edit_mcp.server.tools`` as part of Sub-Spec 3 of the
Stack-Ops feature.
"""
from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_add,
    effect_keyframe_set_rect,
    effect_reorder,
    effects_copy,
    effects_paste,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

# After _add_second_clip runs, (2, 0) is the source (has a transform filter)
# and (1, 0) is a fresh target clip we can paste onto.
SRC = (2, 0)
DST = (1, 0)


def _add_second_clip(project_path: Path) -> None:
    """Append an <entry> to playlist1 so tests have a distinct target clip at (1, 0)."""
    tree = ET.parse(project_path)
    root = tree.getroot()
    playlist1 = None
    for pl in root.findall("playlist"):
        if pl.get("id") == "playlist1":
            playlist1 = pl
            break
    assert playlist1 is not None, "playlist1 not found in fixture"
    entry = ET.SubElement(playlist1, "entry")
    entry.set("producer", "producer0")
    entry.set("in", "0")
    entry.set("out", "299")
    tree.write(project_path, encoding="utf-8", xml_declaration=True)


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Stack Ops Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    _add_second_clip(dest)
    return ws_root, project_name


def _reparse(ws: Path, pf: str):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    return parse_project(ws / pf)


def _effect_names(project, clip_ref):
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    return [e["kdenlive_id"] or e["mlt_service"] for e in patcher.list_effects(project, clip_ref)]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tools_importable_and_callable():
    for name in ("effects_copy", "effects_paste", "effect_reorder"):
        assert callable(getattr(tools, name)), f"{name} missing from tools module"


# ---------------------------------------------------------------------------
# effects_copy
# ---------------------------------------------------------------------------


def test_effects_copy_returns_stack(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    assert out["status"] == "success", out
    data = out["data"]
    assert data["effect_count"] >= 1
    assert data["stack"]["effects"][0]["kdenlive_id"] == "transform"
    assert data["stack"]["source_clip"] == [SRC[0], SRC[1]]


def test_effects_copy_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = effects_copy(workspace_path=str(ws), project_file="nope.kdenlive", track=SRC[0], clip=SRC[1])
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_effects_copy_bad_clip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=99)
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# effects_paste
# ---------------------------------------------------------------------------


def test_copy_paste_round_trip_append(tmp_path):
    ws, pf = _make_ws(tmp_path)
    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    assert copied["status"] == "success"
    source_count = copied["data"]["effect_count"]

    project = _reparse(ws, pf)
    original_target = len(_effect_names(project, DST))

    stack_json = json.dumps(copied["data"]["stack"])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=stack_json, mode="append",
    )
    assert out["status"] == "success", out
    assert out["data"]["effects_pasted"] == source_count
    assert out["data"]["mode"] == "append"
    assert isinstance(out["data"]["snapshot_id"], str)
    assert out["data"]["snapshot_id"]

    project2 = _reparse(ws, pf)
    target_effects = _effect_names(project2, DST)
    assert len(target_effects) == original_target + source_count


def test_paste_prepend_puts_filters_at_front(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Add a known filter to target first
    r = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], effect_name="avfilter.eq",
        params=json.dumps({"av.brightness": "0.1"}),
    )
    assert r["status"] == "success", r

    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    assert copied["status"] == "success"
    source_count = copied["data"]["effect_count"]

    stack_json = json.dumps(copied["data"]["stack"])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=stack_json, mode="prepend",
    )
    assert out["status"] == "success", out
    assert out["data"]["effects_pasted"] == source_count

    project = _reparse(ws, pf)
    names = _effect_names(project, DST)
    # First N are the pasted stack -- first should be 'transform'
    assert names[0] == "transform"


def test_paste_replace_clears_target(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Pre-add a distinctive filter on target
    r = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], effect_name="avfilter.eq",
        params=json.dumps({"av.brightness": "0.1"}),
    )
    assert r["status"] == "success", r

    project = _reparse(ws, pf)
    pre = _effect_names(project, DST)
    assert any("eq" in n for n in pre), f"expected 'eq' filter in {pre}"

    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    source_count = copied["data"]["effect_count"]

    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps(copied["data"]["stack"]),
        mode="replace",
    )
    assert out["status"] == "success", out
    assert out["data"]["effects_pasted"] == source_count

    project2 = _reparse(ws, pf)
    post = _effect_names(project2, DST)
    assert len(post) == source_count
    assert not any("eq" in n for n in post), f"eq should be removed; got {post}"


def test_paste_invalid_json(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack="{not-json", mode="append",
    )
    assert out["status"] == "error"
    assert "effects_copy" in out["message"]


def test_paste_missing_effects_key(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps({"source_clip": [0, 0]}),
        mode="append",
    )
    assert out["status"] == "error"
    assert "effects" in out["message"]


def test_paste_bad_mode(tmp_path):
    ws, pf = _make_ws(tmp_path)
    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps(copied["data"]["stack"]),
        mode="shove",
    )
    assert out["status"] == "error"
    msg = out["message"]
    assert "append" in msg and "prepend" in msg and "replace" in msg


def test_paste_non_existent_clip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=99, stack=json.dumps(copied["data"]["stack"]),
        mode="append",
    )
    assert out["status"] == "error"


def test_paste_returns_snapshot_id_and_dir_exists(tmp_path):
    ws, pf = _make_ws(tmp_path)
    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps(copied["data"]["stack"]),
        mode="append",
    )
    assert out["status"] == "success"
    snap_id = out["data"]["snapshot_id"]
    assert (ws / "projects" / "snapshots" / snap_id).is_dir()


def test_paste_rewrites_track_clip_attrs_in_xml(tmp_path):
    ws, pf = _make_ws(tmp_path)
    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps(copied["data"]["stack"]),
        mode="append",
    )
    assert out["status"] == "success", out

    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = _reparse(ws, pf)
    filters = list(patcher._iter_clip_filters(project, DST))
    assert filters, "no filters on target"
    _idx, elem, _root = filters[-1]
    xml_str = elem.xml_string
    assert f'track="{DST[0]}"' in xml_str, xml_str
    assert f'clip_index="{DST[1]}"' in xml_str, xml_str


# ---------------------------------------------------------------------------
# effect_reorder
# ---------------------------------------------------------------------------


def test_effect_reorder_returns_snapshot_id(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Add a second filter so we have a stack of 2+ on source
    r = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], effect_name="avfilter.eq",
        params=json.dumps({"av.brightness": "0.1"}),
    )
    assert r["status"] == "success", r

    out = effect_reorder(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], from_index=1, to_index=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["from_index"] == 1
    assert out["data"]["to_index"] == 0
    snap_id = out["data"]["snapshot_id"]
    assert isinstance(snap_id, str) and snap_id
    assert (ws / "projects" / "snapshots" / snap_id).is_dir()


def test_effect_reorder_out_of_range(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_reorder(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], from_index=99, to_index=0,
    )
    assert out["status"] == "error", out
    assert "Current stack" in out["message"]


# ---------------------------------------------------------------------------
# Keyframe preservation through MCP layer
# ---------------------------------------------------------------------------


def test_keyframe_preservation_round_trip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([
        {"frame": 0, "value": [0, 0, 1920, 1080, 1], "easing": "linear"},
        {"frame": 30, "value": [100, 100, 1000, 800, 1], "easing": "linear"},
    ])
    kf_out = effect_keyframe_set_rect(
        workspace_path=str(ws), project_file=pf,
        track=SRC[0], clip=SRC[1], effect_index=0, property="rect",
        keyframes=kfs, mode="replace",
    )
    assert kf_out["status"] == "success", kf_out

    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = _reparse(ws, pf)
    source_rect = patcher.get_effect_property(project, SRC, 0, "rect")
    assert source_rect, "source rect property should be set"

    copied = effects_copy(workspace_path=str(ws), project_file=pf, track=SRC[0], clip=SRC[1])
    assert copied["status"] == "success"
    paste_out = effects_paste(
        workspace_path=str(ws), project_file=pf,
        track=DST[0], clip=DST[1], stack=json.dumps(copied["data"]["stack"]),
        mode="append",
    )
    assert paste_out["status"] == "success", paste_out

    project2 = _reparse(ws, pf)
    names = _effect_names(project2, DST)
    transform_idx = None
    for i, name in enumerate(names):
        if name == "transform":
            transform_idx = i
    assert transform_idx is not None, f"no transform on target: {names}"
    pasted_rect = patcher.get_effect_property(project2, DST, transform_idx, "rect")
    assert pasted_rect == source_rect, (
        f"rect mismatch:\n  source={source_rect!r}\n  pasted={pasted_rect!r}"
    )
