"""Integration tests for semantic reorder wrappers.

Covers ``move_to_top``, ``move_to_bottom``, ``move_up``, ``move_down``
registered in ``workshop_video_brain.edit_mcp.server.tools``.

Test plan: SR-24..SR-34 (SR-35 is the global regression suite).
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
    move_down,
    move_to_bottom,
    move_to_top,
    move_up,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

# (2, 0) is the source (has a transform filter baseline).
CLIP = (2, 0)


def _add_second_clip(project_path: Path) -> None:
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
    result = workspace_create(title="Reorder Wrappers Test", media_root=str(media_root))
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


def _build_four_filter_stack(ws: Path, pf: str) -> list[str]:
    """Starting from the fixture (which has 1 transform filter on (2,0)),
    add 3 more distinct filters so we have a 4-filter stack. Returns the
    stack names in order.
    """
    extras = [
        ("avfilter.eq", {"av.brightness": "0.1"}),
        ("avfilter.hue", {"av.h": "45"}),
        ("avfilter.negate", {}),
    ]
    for name, params in extras:
        r = effect_add(
            workspace_path=str(ws), project_file=pf,
            track=CLIP[0], clip=CLIP[1], effect_name=name,
            params=json.dumps(params),
        )
        assert r["status"] == "success", r
    project = _reparse(ws, pf)
    names = _effect_names(project, CLIP)
    assert len(names) == 4, f"expected 4 filters, got {names}"
    return names


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tools_importable_and_callable():
    for name in ("move_to_top", "move_to_bottom", "move_up", "move_down"):
        assert callable(getattr(tools, name)), f"{name} missing"


# ---------------------------------------------------------------------------
# SR-24: move_to_top happy path
# ---------------------------------------------------------------------------


def test_move_to_top_moves_filter_to_index_0(tmp_path):
    ws, pf = _make_ws(tmp_path)
    names_before = _build_four_filter_stack(ws, pf)
    target = names_before[3]

    out = move_to_top(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=3,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == 3
    assert out["data"]["effect_index_after"] == 0
    assert out["data"]["snapshot_id"]

    project = _reparse(ws, pf)
    names_after = _effect_names(project, CLIP)
    assert names_after[0] == target


# ---------------------------------------------------------------------------
# SR-25: move_to_bottom happy path
# ---------------------------------------------------------------------------


def test_move_to_bottom_moves_filter_to_last_index(tmp_path):
    ws, pf = _make_ws(tmp_path)
    names_before = _build_four_filter_stack(ws, pf)
    target = names_before[0]

    out = move_to_bottom(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == 0
    assert out["data"]["effect_index_after"] == 3
    assert out["data"]["snapshot_id"]

    project = _reparse(ws, pf)
    names_after = _effect_names(project, CLIP)
    assert names_after[-1] == target


# ---------------------------------------------------------------------------
# SR-26: move_up happy path
# ---------------------------------------------------------------------------


def test_move_up_decrements_index(tmp_path):
    ws, pf = _make_ws(tmp_path)
    names_before = _build_four_filter_stack(ws, pf)
    target = names_before[2]

    out = move_up(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=2,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == 2
    assert out["data"]["effect_index_after"] == 1

    project = _reparse(ws, pf)
    names_after = _effect_names(project, CLIP)
    assert names_after[1] == target


# ---------------------------------------------------------------------------
# SR-27: move_down happy path
# ---------------------------------------------------------------------------


def test_move_down_increments_index(tmp_path):
    ws, pf = _make_ws(tmp_path)
    names_before = _build_four_filter_stack(ws, pf)
    target = names_before[0]

    out = move_down(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == 0
    assert out["data"]["effect_index_after"] == 1

    project = _reparse(ws, pf)
    names_after = _effect_names(project, CLIP)
    assert names_after[1] == target


# ---------------------------------------------------------------------------
# SR-28: move_up at top -> no-op
# ---------------------------------------------------------------------------


def test_move_up_at_top_is_noop_with_note(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    out = move_up(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == out["data"]["effect_index_after"] == 0
    assert out["data"]["note"] == "already at top"
    assert out["data"]["snapshot_id"] is None


# ---------------------------------------------------------------------------
# SR-29: move_down at bottom -> no-op
# ---------------------------------------------------------------------------


def test_move_down_at_bottom_is_noop_with_note(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    out = move_down(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=3,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index_before"] == out["data"]["effect_index_after"] == 3
    assert out["data"]["note"] == "already at bottom"
    assert out["data"]["snapshot_id"] is None


# ---------------------------------------------------------------------------
# SR-30: move_to_top at top -> no-op
# ---------------------------------------------------------------------------


def test_move_to_top_at_top_is_noop(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    out = move_to_top(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=0,
    )
    assert out["status"] == "success", out
    assert out["data"]["note"] == "already at top"
    assert out["data"]["snapshot_id"] is None


# ---------------------------------------------------------------------------
# SR-31: move_to_bottom at bottom -> no-op
# ---------------------------------------------------------------------------


def test_move_to_bottom_at_bottom_is_noop(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    out = move_to_bottom(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=3,
    )
    assert out["status"] == "success", out
    assert out["data"]["note"] == "already at bottom"
    assert out["data"]["snapshot_id"] is None


# ---------------------------------------------------------------------------
# SR-32: out-of-range effect_index -> err naming stack length
# ---------------------------------------------------------------------------


def test_out_of_range_effect_index_returns_err_with_stack_length(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    for fn in (move_to_top, move_to_bottom, move_up, move_down):
        out = fn(
            workspace_path=str(ws), project_file=pf,
            track=CLIP[0], clip=CLIP[1], effect_index=99,
        )
        assert out["status"] == "error", (fn.__name__, out)
        assert "4" in out["message"], (fn.__name__, out["message"])
        assert "out of range" in out["message"], (fn.__name__, out["message"])

    # negative is also out of range
    out = move_to_top(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=-1,
    )
    assert out["status"] == "error"
    assert "4" in out["message"]


# ---------------------------------------------------------------------------
# SR-33: single-filter stack -> all four are no-ops
# ---------------------------------------------------------------------------


def test_single_filter_stack_all_four_are_noops(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Fixture already has exactly 1 transform filter on (2, 0)
    project = _reparse(ws, pf)
    assert len(_effect_names(project, CLIP)) == 1

    for fn, expected_note in (
        (move_to_top, "already at top"),
        (move_up, "already at top"),
        (move_to_bottom, "already at bottom"),
        (move_down, "already at bottom"),
    ):
        out = fn(
            workspace_path=str(ws), project_file=pf,
            track=CLIP[0], clip=CLIP[1], effect_index=0,
        )
        assert out["status"] == "success", (fn.__name__, out)
        assert out["data"]["note"] == expected_note, (fn.__name__, out)
        assert out["data"]["effect_index_before"] == 0
        assert out["data"]["effect_index_after"] == 0
        assert out["data"]["snapshot_id"] is None


# ---------------------------------------------------------------------------
# SR-34: return shape -- snapshot_id exists on disk for writes
# ---------------------------------------------------------------------------


def test_each_write_returns_valid_snapshot_id(tmp_path):
    ws, pf = _make_ws(tmp_path)
    _build_four_filter_stack(ws, pf)

    # move_to_top from index 3
    out = move_to_top(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=3,
    )
    assert out["status"] == "success"
    snap = out["data"]["snapshot_id"]
    assert isinstance(snap, str) and snap
    assert (ws / "projects" / "snapshots" / snap).is_dir()

    # move_down from index 0
    out = move_down(
        workspace_path=str(ws), project_file=pf,
        track=CLIP[0], clip=CLIP[1], effect_index=0,
    )
    assert out["status"] == "success"
    snap = out["data"]["snapshot_id"]
    assert isinstance(snap, str) and snap
    assert (ws / "projects" / "snapshots" / snap).is_dir()

    # Verify return shape keys
    assert set(out["data"].keys()) >= {
        "effect_index_before", "effect_index_after", "snapshot_id",
    }
