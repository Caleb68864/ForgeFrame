"""effect_add accepts JSON numbers and booleans in params (its docstring's own example)."""
from __future__ import annotations

from tests._testkit import call_tool, solid_color_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server.tools.effects_catalog import effect_add
from workshop_video_brain.workspace.manager import WorkspaceManager


def test_numeric_and_boolean_params_are_written_as_strings(tmp_path):
    root = tmp_path / "ws"
    WorkspaceManager.create("FX", tmp_path, workspace_root=root)
    rel = "projects/working_copies/fx_v1.kdenlive"
    serialize_project(solid_color_project(), root / rel)

    result = call_tool(effect_add, str(root), rel, 0, 0, "brightness",
                       '{"level": 0.5, "alpha": 1, "custom_flag": true}', allow_unregistered=True)

    assert result["status"] == "success", result
    props = list_effects(parse_project(root / rel), (0, 0))[0]["properties"]
    assert (props["level"], props["alpha"], props["custom_flag"]) == ("0.5", "1", "1")
