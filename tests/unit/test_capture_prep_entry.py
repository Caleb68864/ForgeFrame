"""Entry points for capture prep: the ``capture_prep_checklist`` MCP tool and
the ``wvb plan capture-prep`` CLI command (roadmap next #7).

Both are thin shells over ``production_brain.skills.capture_prep``; these tests
check the workspace plumbing (shot plan loading, generic fallback, error
envelopes / exit codes) and that the generator's own input validation reaches
the caller unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests._testkit import assert_registered, call_tool
from workshop_video_brain.app.cli import main
from workshop_video_brain.production_brain.skills.capture_prep import (
    load_shot_plan,
)


SHOT_PLAN = {
    "title": "Dovetail Joint Tutorial",
    "a_roll": [
        {"id": "A1", "type": "a_roll", "description": "Intro on-camera",
         "beat_ref": "GENERAL", "priority": "must-have", "notes": ""},
    ],
    "overhead": [
        {"id": "O1", "type": "overhead", "description": "Layout marking",
         "beat_ref": "Step 1", "priority": "must-have", "notes": ""},
    ],
    "closeups": [], "measurements": [], "inserts": [], "glamour": [],
    "pickups": [],
}


def _workspace(tmp_path: Path, plan: dict | str | None = SHOT_PLAN) -> Path:
    ws = tmp_path / "ws"
    (ws / "reports").mkdir(parents=True)
    if plan is not None:
        text = plan if isinstance(plan, str) else json.dumps(plan)
        (ws / "reports" / "shot_plan.json").write_text(text, encoding="utf-8")
    return ws


def _tool():
    from workshop_video_brain.edit_mcp.server.bundles import capture_prep

    return capture_prep.capture_prep_checklist


# ---------------------------------------------------------------------------
# load_shot_plan (shared by both shells)
# ---------------------------------------------------------------------------

class TestLoadShotPlan:
    def test_reads_reports_shot_plan(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        plan, source = load_shot_plan(ws)
        assert plan["title"] == "Dovetail Joint Tutorial"
        assert source == ws / "reports" / "shot_plan.json"

    def test_missing_plan_falls_back_to_generic(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan=None)
        plan, source = load_shot_plan(ws)
        assert source is None
        assert plan["title"] == "Generic Shoot"
        assert all(plan[k] == [] for k in ("a_roll", "overhead", "pickups"))

    def test_generic_plan_is_a_fresh_copy(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan=None)
        plan, _ = load_shot_plan(ws)
        plan["a_roll"].append({"id": "X"})
        again, _ = load_shot_plan(ws)
        assert again["a_roll"] == []

    def test_malformed_json_raises_value_error(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan="{not json")
        with pytest.raises(ValueError, match="shot_plan.json"):
            load_shot_plan(ws)

    def test_non_object_json_raises_value_error(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan="[1, 2]")
        with pytest.raises(ValueError, match="shot_plan.json"):
            load_shot_plan(ws)


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------

class TestCapturePrepTool:
    def test_registered(self):
        assert_registered("capture_prep_checklist")

    def test_ok_payload_from_shot_plan(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = call_tool(_tool(), str(ws), "3840x2160", 24)
        assert result["status"] == "success", result
        data = result["data"]
        assert data["title"] == "Dovetail Joint Tutorial"
        assert data["shot_plan_path"] == str(ws / "reports" / "shot_plan.json")
        assert data["shot_count"] == 2
        assert data["target_resolution"] == "3840x2160"
        assert data["target_fps"] == 24
        md = data["markdown"]
        assert md.startswith("# Capture Prep Checklist: Dovetail Joint Tutorial")
        assert "3840x2160" in md and "1/48" in md
        assert "**O1**" in md and "**A1**" in md

    def test_defaults(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        data = call_tool(_tool(), str(ws))["data"]
        assert data["target_resolution"] == "1920x1080"
        assert data["target_fps"] == 30

    def test_generic_checklist_without_shot_plan(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan=None)
        result = call_tool(_tool(), str(ws))
        assert result["status"] == "success", result
        data = result["data"]
        assert data["shot_plan_path"] is None
        assert data["shot_count"] == 0
        assert "Generic Shoot" in data["markdown"]
        assert "shot_plan.json" in data["note"]

    def test_tool_does_not_write_files(self, tmp_path: Path):
        ws = _workspace(tmp_path)
        before = sorted(p.relative_to(ws) for p in ws.rglob("*"))
        call_tool(_tool(), str(ws))
        assert sorted(p.relative_to(ws) for p in ws.rglob("*")) == before

    def test_missing_workspace(self, tmp_path: Path):
        result = call_tool(_tool(), str(tmp_path / "ghost"))
        assert result["status"] == "error"
        assert result["error_type"] == "missing_file"

    def test_empty_workspace_path(self):
        result = call_tool(_tool(), "")
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"

    @pytest.mark.parametrize("fps", [0, -30, 29.97, 23.976, True])
    def test_bad_fps_uses_generator_validation(self, tmp_path: Path, fps):
        ws = _workspace(tmp_path)
        result = call_tool(_tool(), str(ws), "1920x1080", fps)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"
        assert "target_fps must be a positive integer" in result["message"]
        assert "24, 30 or 60" in result["suggestion"]

    @pytest.mark.parametrize("res", ["1080p", "1920x", "x1080", "0x1080", ""])
    def test_bad_resolution_uses_generator_validation(self, tmp_path: Path, res):
        ws = _workspace(tmp_path)
        result = call_tool(_tool(), str(ws), res, 30)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"
        assert "target_resolution must look like" in result["message"]

    def test_malformed_shot_plan(self, tmp_path: Path):
        ws = _workspace(tmp_path, plan="{not json")
        result = call_tool(_tool(), str(ws))
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"
        assert "shot_plan.json" in result["message"]


# ---------------------------------------------------------------------------
# CLI: wvb plan capture-prep
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCapturePrepCli:
    def test_listed_under_plan(self, runner: CliRunner):
        result = runner.invoke(main, ["plan", "--help"])
        assert result.exit_code == 0
        assert "capture-prep" in result.output

    def test_help_lists_options(self, runner: CliRunner):
        result = runner.invoke(main, ["plan", "capture-prep", "--help"])
        assert result.exit_code == 0
        for flag in ("--target-resolution", "--target-fps", "--json"):
            assert flag in result.output

    def test_prints_markdown(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = runner.invoke(
            main,
            ["plan", "capture-prep", str(ws),
             "--target-resolution", "3840x2160", "--target-fps", "60"],
        )
        assert result.exit_code == 0, result.output
        assert "# Capture Prep Checklist: Dovetail Joint Tutorial" in result.output
        assert "3840x2160" in result.output and "1/120" in result.output

    def test_json_output(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = runner.invoke(main, ["plan", "capture-prep", str(ws), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["title"] == "Dovetail Joint Tutorial"
        assert data["target_fps"] == 30
        assert data["shot_count"] == 2

    def test_generic_without_shot_plan(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path, plan=None)
        result = runner.invoke(main, ["plan", "capture-prep", str(ws)])
        assert result.exit_code == 0, result.output
        assert "Generic Shoot" in result.output

    def test_zero_fps_rejected_by_generator(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = runner.invoke(
            main, ["plan", "capture-prep", str(ws), "--target-fps", "0"]
        )
        assert result.exit_code == 1
        assert "target_fps must be a positive integer" in result.output

    def test_fractional_fps_rejected(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = runner.invoke(
            main, ["plan", "capture-prep", str(ws), "--target-fps", "29.97"]
        )
        assert result.exit_code != 0
        assert "Capture Prep Checklist" not in result.output

    def test_bad_resolution(self, runner: CliRunner, tmp_path: Path):
        ws = _workspace(tmp_path)
        result = runner.invoke(
            main, ["plan", "capture-prep", str(ws), "--target-resolution", "4k"]
        )
        assert result.exit_code == 1
        assert "target_resolution must look like" in result.output

    def test_missing_workspace(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(main, ["plan", "capture-prep", str(tmp_path / "ghost")])
        assert result.exit_code == 1
        assert "does not exist" in result.output
