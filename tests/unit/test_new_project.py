"""Unit tests for the new_project pipeline."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.new_project import (
    create_new_project,
    list_projects,
)
from workshop_video_brain.workspace.folders import WORKSPACE_FOLDERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, title: str = "Zippered Pouch Tutorial", **kwargs):
    """Helper: create a project with a tmp_path-based projects_root."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    return create_new_project(
        title=title,
        projects_root=projects_root,
        vault_path=None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Workspace folder structure
# ---------------------------------------------------------------------------


class TestWorkspaceCreated:
    def test_workspace_directory_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert Path(result.workspace_path).is_dir()

    def test_workspace_path_contains_slug(self, tmp_path: Path):
        result = _make_project(tmp_path, title="My Test Video")
        assert "my-test-video" in result.workspace_path

    def test_standard_workspace_folders_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        workspace = Path(result.workspace_path)
        for folder in WORKSPACE_FOLDERS:
            assert (workspace / folder).is_dir(), f"Missing standard folder: {folder}"

    def test_intake_folder_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert (Path(result.workspace_path) / "intake").is_dir()

    def test_media_raw_video_folder_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert (Path(result.workspace_path) / "media" / "raw" / "video").is_dir()

    def test_media_raw_audio_folder_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert (Path(result.workspace_path) / "media" / "raw" / "audio").is_dir()

    def test_media_raw_images_folder_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert (Path(result.workspace_path) / "media" / "raw" / "images").is_dir()

    def test_media_folders_listed_in_result(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert isinstance(result.media_folders_created, list)
        assert len(result.media_folders_created) > 0


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


class TestSlugGeneration:
    def test_slug_lowercase(self, tmp_path: Path):
        result = _make_project(tmp_path, title="Zippered Bikepacking Pouch")
        assert result.project_slug == result.project_slug.lower()

    def test_slug_hyphenated(self, tmp_path: Path):
        result = _make_project(tmp_path, title="Zippered Bikepacking Pouch")
        assert result.project_slug == "zippered-bikepacking-pouch"

    def test_slug_special_chars_removed(self, tmp_path: Path):
        result = _make_project(tmp_path, title="X-Pac Pouch (DIY!)")
        assert " " not in result.project_slug
        assert "(" not in result.project_slug
        assert "!" not in result.project_slug

    def test_title_preserved_in_result(self, tmp_path: Path):
        result = _make_project(tmp_path, title="Cool Build Video")
        assert result.project_title == "Cool Build Video"


# ---------------------------------------------------------------------------
# Vault note
# ---------------------------------------------------------------------------


class TestVaultNote:
    def test_vault_note_created_when_vault_path_given(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        result = create_new_project(
            title="My Build Video",
            projects_root=projects_root,
            vault_path=vault,
        )
        assert result.vault_note_path != ""
        assert Path(result.vault_note_path).exists()

    def test_vault_note_in_in_progress_folder(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        result = create_new_project(
            title="Stove Bag Build",
            projects_root=projects_root,
            vault_path=vault,
        )
        assert "In Progress" in result.vault_note_path

    def test_no_vault_path_no_note_with_warning(self, tmp_path: Path, monkeypatch):
        # Isolate from real config / env by removing WVB_VAULT_PATH and patching
        # _read_config to return no vault_path.
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        import workshop_video_brain.edit_mcp.pipelines.new_project as _np
        monkeypatch.setattr(_np, "_read_config", lambda: {})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = create_new_project(
                title="Zippered Pouch Tutorial",
                projects_root=tmp_path / "projects",
                vault_path=None,
            )
        assert result.vault_note_path == ""
        warning_messages = [str(w.message) for w in caught]
        assert any("vault" in m.lower() for m in warning_messages)

    def test_brain_dump_in_vault_note(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        brain_dump = "Make a lightweight stove bag from X-Pac fabric"
        result = create_new_project(
            title="Stove Bag",
            brain_dump=brain_dump,
            projects_root=projects_root,
            vault_path=vault,
        )
        note_content = Path(result.vault_note_path).read_text(encoding="utf-8")
        assert brain_dump in note_content


# ---------------------------------------------------------------------------
# Brain dump → outline / script / shot plan
# ---------------------------------------------------------------------------


class TestPlanningGeneration:
    def test_outline_generated_when_brain_dump_provided(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Make a walnut cutting board")
        assert result.outline_generated is True

    def test_script_generated_from_outline(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Make a walnut cutting board")
        assert result.script_generated is True

    def test_shot_plan_generated_from_script(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Make a walnut cutting board")
        assert result.shot_plan_generated is True

    def test_outline_json_saved_to_reports(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Build a tool cabinet")
        outline_path = Path(result.workspace_path) / "reports" / "outline.json"
        assert outline_path.exists()
        data = json.loads(outline_path.read_text())
        assert isinstance(data, dict)
        assert "teaching_beats" in data

    def test_script_json_saved_to_reports(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Build a tool cabinet")
        script_path = Path(result.workspace_path) / "reports" / "script.json"
        assert script_path.exists()
        data = json.loads(script_path.read_text())
        assert isinstance(data, dict)
        assert "steps" in data

    def test_shot_plan_json_saved_to_reports(self, tmp_path: Path):
        result = _make_project(tmp_path, brain_dump="Build a tool cabinet")
        shot_plan_path = Path(result.workspace_path) / "reports" / "shot_plan.json"
        assert shot_plan_path.exists()
        data = json.loads(shot_plan_path.read_text())
        assert isinstance(data, dict)
        assert "a_roll" in data

    def test_no_brain_dump_no_outline(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert result.outline_generated is False

    def test_no_brain_dump_no_script(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert result.script_generated is False

    def test_no_brain_dump_no_shot_plan(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert result.shot_plan_generated is False

    def test_no_brain_dump_workspace_still_created(self, tmp_path: Path):
        result = _make_project(tmp_path)
        assert Path(result.workspace_path).is_dir()

    def test_brain_dump_preserved_in_result(self, tmp_path: Path):
        brain_dump = "Sew a bikepacking frame bag from ripstop nylon"
        result = _make_project(tmp_path, brain_dump=brain_dump)
        assert result.brain_dump == brain_dump


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_list_projects_returns_list(self, tmp_path: Path):
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        result = list_projects(projects_root=projects_root)
        assert isinstance(result, list)

    def test_list_projects_empty_when_no_projects(self, tmp_path: Path):
        projects_root = tmp_path / "empty-projects"
        projects_root.mkdir()
        result = list_projects(projects_root=projects_root)
        assert result == []

    def test_list_projects_nonexistent_root_returns_empty(self, tmp_path: Path):
        result = list_projects(projects_root=tmp_path / "does-not-exist")
        assert result == []

    def test_list_projects_finds_created_project(self, tmp_path: Path):
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        create_new_project(
            title="My Test Tutorial",
            projects_root=projects_root,
            vault_path=None,
        )
        projects = list_projects(projects_root=projects_root)
        assert len(projects) == 1
        assert projects[0]["name"] == "My Test Tutorial"
        assert projects[0]["slug"] == "my-test-tutorial"

    def test_list_projects_finds_multiple_projects(self, tmp_path: Path):
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            create_new_project(title="Video One", projects_root=projects_root, vault_path=None)
            create_new_project(title="Video Two", projects_root=projects_root, vault_path=None)
        projects = list_projects(projects_root=projects_root)
        assert len(projects) == 2
        names = {p["name"] for p in projects}
        assert "Video One" in names
        assert "Video Two" in names

    def test_list_projects_result_has_expected_keys(self, tmp_path: Path):
        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        create_new_project(
            title="Key Check Project",
            projects_root=projects_root,
            vault_path=None,
        )
        projects = list_projects(projects_root=projects_root)
        p = projects[0]
        assert "name" in p
        assert "slug" in p
        assert "status" in p
        assert "workspace_path" in p
        assert "vault_note_path" in p
