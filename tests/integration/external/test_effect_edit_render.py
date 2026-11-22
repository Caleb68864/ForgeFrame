"""Real melt: editing an applied effect changes what renders (prompt 19).

A disabled effect stops changing pixels and stays in the file with
``disable=1``; removing it does the same; a parameter edit is visible.
Effects are added through ``effect_add`` (so they carry prompt 03's Kdenlive
identity) and edited through the new tools.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import RED, call_tool, requires_melt, solid_color_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server.bundles.effect_edit import (
    effect_param_set,
    effect_remove,
    effect_toggle,
)
from workshop_video_brain.edit_mcp.server.tools.effects_catalog import effect_add
from workshop_video_brain.workspace.manager import WorkspaceManager

from ._oracle import frames_differ, frames_similar, mean_color, render_frame

pytestmark = [pytest.mark.external, requires_melt]

FRAME = 10
REL = "projects/working_copies/fx_v1.kdenlive"


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("FX", tmp_path, workspace_root=root)
    serialize_project(solid_color_project(color=RED), root / REL)
    return root


def _frame(ws: Path, render_dir: Path, name: str, melt_bin: str) -> Path:
    return render_frame(ws / REL, FRAME, render_dir, melt_bin=melt_bin, name=f"{name}.png")


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_toggle_and_remove_negate(ws, melt_bin, render_dir: Path):
    plain = _frame(ws, render_dir, "plain", melt_bin)
    _ok(call_tool(effect_add, str(ws), REL, 0, 0, "avfilter.negate", allow_unregistered=True))
    negated = _frame(ws, render_dir, "negated", melt_bin)
    assert frames_differ(plain, negated), "negate did not change the frame"

    _ok(call_tool(effect_toggle, str(ws), REL, 0, 0, False, effect_name="avfilter.negate"))
    stack = list_effects(parse_project(ws / REL), (0, 0))
    assert len(stack) == 1 and stack[0]["properties"]["disable"] == "1"
    assert frames_similar(plain, _frame(ws, render_dir, "off", melt_bin)), "disabled negate still renders"

    _ok(call_tool(effect_toggle, str(ws), REL, 0, 0, True, effect_index=0))
    assert frames_differ(plain, _frame(ws, render_dir, "on_again", melt_bin)), "re-enabled negate is a no-op"

    _ok(call_tool(effect_remove, str(ws), REL, 0, 0, effect_index=0))
    assert list_effects(parse_project(ws / REL), (0, 0)) == []
    assert frames_similar(plain, _frame(ws, render_dir, "removed", melt_bin))


def test_param_set_dims_brightness(ws, melt_bin, render_dir: Path):
    _ok(call_tool(effect_add, str(ws), REL, 0, 0, "brightness", '{"level": "1.0"}', allow_unregistered=True))
    bright = mean_color(_frame(ws, render_dir, "level_1", melt_bin))
    _ok(call_tool(effect_param_set, str(ws), REL, 0, 0, '{"level": 0.3}', effect_name="brightness"))
    dim = mean_color(_frame(ws, render_dir, "level_03", melt_bin))
    assert dim[0] < 0.7 * bright[0], f"red {bright[0]:.1f} -> {dim[0]:.1f}"
