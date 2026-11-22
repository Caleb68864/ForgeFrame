"""Edit effects already applied to a clip (prompt 19)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, sequence_project
from workshop_video_brain.core.models.timeline import (
    AddEffect,
    RemoveEffect,
    SetEffectEnabled,
    SetEffectParams,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines.effect_edit import describe_effect, is_keyframed
from workshop_video_brain.edit_mcp.server.bundles.effect_edit import (
    effect_list_applied,
    effect_param_get,
    effect_param_set,
    effect_remove,
    effect_toggle,
)
from workshop_video_brain.workspace.manager import WorkspaceManager

REL = "projects/working_copies/fx_v1.kdenlive"


def _project():
    """Two clips on the video track; clip 0 has brightness + negate, clip 1 has brightness."""
    project = sequence_project()
    return patch_project(project, [
        AddEffect(track_index=0, clip_index=0, effect_name="brightness", params={"level": "1"}),
        AddEffect(track_index=0, clip_index=0, effect_name="avfilter.negate"),
        AddEffect(track_index=0, clip_index=1, effect_name="brightness", params={"level": "1"}),
    ])


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("FX", tmp_path, workspace_root=root)
    serialize_project(_project(), root / REL)
    return root


def _stack(root: Path, clip: int = 0) -> list[dict]:
    return [describe_effect(e) for e in list_effects(parse_project(root / REL), (0, clip))]


def _ok(result: dict) -> dict:
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("effect_list_applied", "effect_param_get", "effect_param_set",
                      "effect_toggle", "effect_remove")


# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------

def _props(project, clip):
    return [e["properties"] for e in list_effects(project, (0, clip))]


def test_intents_touch_only_the_target():
    project = _project()
    other = _props(project, 1)
    patched = patch_project(project, [
        SetEffectParams(track_index=0, clip_index=0, effect_index=0, params={"level": "0.3"}),
        SetEffectEnabled(track_index=0, clip_index=0, effect_index=1, enabled=False),
    ])
    stack = _props(patched, 0)
    assert stack[0]["level"] == "0.3" and "disable" not in stack[0]
    assert stack[1]["disable"] == "1"
    assert _props(patched, 1) == other
    assert _props(project, 0)[0]["level"] == "1"  # input never mutated

    enabled = patch_project(patched, [SetEffectEnabled(track_index=0, clip_index=0, effect_index=1)])
    assert _props(enabled, 0)[1]["disable"] == "0"  # written as 0, not deleted

    removed = patch_project(project, [RemoveEffect(track_index=0, clip_index=0, effect_index=0)])
    assert [e["mlt_service"] for e in list_effects(removed, (0, 0))] == ["avfilter.negate"]
    assert _props(removed, 1) == other


@pytest.mark.parametrize("intent", [
    SetEffectParams(track_index=0, clip_index=0, effect_index=9, params={"level": "1"}),
    SetEffectEnabled(track_index=0, clip_index=0, effect_index=9, enabled=False),
    RemoveEffect(track_index=0, clip_index=5, effect_index=0),
])
def test_out_of_range_is_skipped(intent):
    _patched, report = patch_project(_project(), [intent], with_report=True)
    assert report.all_skipped


def test_keyframe_detection():
    assert is_keyframed("00:00:00.000=1;00:00:01.000=0")
    assert is_keyframed("0=1;25=0.5")
    assert is_keyframed("00:00:00.000~=0.5")
    assert not is_keyframed("0.5")
    assert not is_keyframed("0 0 1920 1080 1")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def test_list_applied(ws):
    data = _ok(call_tool(effect_list_applied, str(ws), REL, 0, 0))
    assert [(e["index"], e["mlt_service"], e["enabled"]) for e in data["effects"]] == [
        (0, "brightness", True), (1, "avfilter.negate", True)]
    assert data["effects"][0]["static_params"]["level"] == "1"
    assert "mlt_service" not in data["effects"][0]["static_params"]


def test_param_get_by_name_and_index(ws):
    by_name = _ok(call_tool(effect_param_get, str(ws), REL, 0, 0, effect_name="brightness", param="level"))
    by_index = _ok(call_tool(effect_param_get, str(ws), REL, 0, 0, effect_index=0, param="level"))
    assert by_name == by_index == {"effect_index": 0, "param": "level", "value": "1", "keyframed": False}
    whole = _ok(call_tool(effect_param_get, str(ws), REL, 0, 0, effect_index=1))
    assert whole["mlt_service"] == "avfilter.negate"
    missing = call_tool(effect_param_get, str(ws), REL, 0, 0, effect_index=0, param="nope")
    assert missing["error_type"] == "not_found" and "level" in missing["suggestion"]


def test_identifier_errors(ws):
    both = call_tool(effect_param_get, str(ws), REL, 0, 0, effect_index=0, effect_name="brightness")
    neither = call_tool(effect_param_get, str(ws), REL, 0, 0)
    assert both["error_type"] == neither["error_type"] == "invalid_input"
    unknown = call_tool(effect_toggle, str(ws), REL, 0, 0, False, effect_name="avfilter.gblur")
    assert unknown["error_type"] == "not_found"
    past = call_tool(effect_remove, str(ws), REL, 0, 0, effect_index=7)
    assert past["error_type"] == "invalid_index"
    bad_clip = call_tool(effect_list_applied, str(ws), REL, 0, 9)
    assert bad_clip["error_type"] == "invalid_index"


def test_ambiguous_name(tmp_path):
    root = tmp_path / "ws"
    WorkspaceManager.create("FX", tmp_path, workspace_root=root)
    project = patch_project(_project(), [AddEffect(track_index=0, clip_index=0, effect_name="brightness")])
    serialize_project(project, root / REL)
    result = call_tool(effect_toggle, str(root), REL, 0, 0, False, effect_name="brightness")
    assert result["error_type"] == "invalid_input" and "Ambiguous" in result["message"]


def test_param_set_round_trip_and_refusals(ws):
    before = (ws / REL).read_bytes()
    for params, needle in [
        ('{"disable": 1}', "effect_toggle"),
        ('{"mlt_service": "x"}', "identify the effect"),
        ('{"levle": 0.3}', "force=true"),
    ]:
        result = call_tool(effect_param_set, str(ws), REL, 0, 0, params, effect_index=0)
        assert result["error_type"] == "invalid_input", result
        assert needle in result["suggestion"], result
    assert call_tool(effect_param_set, str(ws), REL, 0, 0, "{bad", effect_index=0)["error_type"] == "bad_json_param"
    assert (ws / REL).read_bytes() == before

    data = _ok(call_tool(effect_param_set, str(ws), REL, 0, 0, '{"level": 0.3}', effect_name="brightness"))
    assert data["old"] == {"level": "1"} and data["new"] == {"level": "0.3"} and data["snapshot_id"]
    assert _stack(ws)[0]["static_params"]["level"] == "0.3"
    assert _stack(ws, 1)[0]["static_params"]["level"] == "1"  # other clip untouched

    forced = _ok(call_tool(effect_param_set, str(ws), REL, 0, 0, '{"custom_x": true}',
                           effect_index=0, force=True))
    assert forced["new"] == {"custom_x": "1"}


def test_keyframed_param_is_refused(ws):
    project = parse_project(ws / REL)
    patched = patch_project(project, [SetEffectParams(track_index=0, clip_index=0, effect_index=0,
                                                      params={"level": "00:00:00.000=1;00:00:01.000=0"})])
    serialize_project(patched, ws / REL)
    got = _ok(call_tool(effect_param_get, str(ws), REL, 0, 0, effect_index=0, param="level"))
    assert got["keyframed"] is True
    result = call_tool(effect_param_set, str(ws), REL, 0, 0, '{"level": 0.5}', effect_index=0)
    assert result["error_type"] == "invalid_input"
    assert "effect_keyframe_set_scalar" in result["suggestion"]


def test_toggle_round_trip(ws):
    off = _ok(call_tool(effect_toggle, str(ws), REL, 0, 0, False, effect_name="avfilter.negate"))
    assert (off["was_enabled"], off["enabled"]) == (True, False)
    assert list_effects(parse_project(ws / REL), (0, 0))[1]["properties"]["disable"] == "1"
    assert _stack(ws)[1]["enabled"] is False
    on = _ok(call_tool(effect_toggle, str(ws), REL, 0, 0, True, effect_index=1))
    assert (on["was_enabled"], on["enabled"]) == (False, True)
    assert list_effects(parse_project(ws / REL), (0, 0))[1]["properties"]["disable"] == "0"


def test_remove(ws):
    data = _ok(call_tool(effect_remove, str(ws), REL, 0, 0, effect_name="avfilter.negate"))
    assert data["removed"]["mlt_service"] == "avfilter.negate"
    assert data["stack_length"] == 1
    assert [e["mlt_service"] for e in _stack(ws)] == ["brightness"]
    assert len(_stack(ws, 1)) == 1


def test_project_file_errors(ws):
    assert call_tool(effect_list_applied, str(ws), "nope.kdenlive", 0, 0)["error_type"] == "missing_file"
    (ws / "bad.kdenlive").write_text("<not xml")
    assert call_tool(effect_list_applied, str(ws), "bad.kdenlive", 0, 0)["error_type"] == "corrupt_project"
    assert json.loads(json.dumps(call_tool(effect_list_applied, str(ws), REL, 0, 0)))  # JSON-safe
