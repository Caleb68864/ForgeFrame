"""Tests for Workspace construction, nested VideoProject, and serialization (MD-16)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.project import VideoProject
from workshop_video_brain.core.models.workspace import Workspace


def _make_project(**kwargs) -> VideoProject:
    return VideoProject(title="Test Project", **kwargs)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

def test_workspace_required():
    project = _make_project()

    with pytest.raises(ValidationError):
        Workspace()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        Workspace(project=project, media_root="/media")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        Workspace(project=project, workspace_root="/workspace")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        Workspace(media_root="/media", workspace_root="/workspace")  # type: ignore[call-arg]


def test_workspace_defaults():
    project = _make_project()
    ws = Workspace(project=project, media_root="/media", workspace_root="/workspace")
    assert ws.vault_note_path == ""
    assert ws.config == {}


def test_workspace_id_auto_generated():
    project = _make_project()
    ws1 = Workspace(project=project, media_root="/m", workspace_root="/w")
    ws2 = Workspace(project=project, media_root="/m", workspace_root="/w")
    assert ws1.id != ws2.id


def test_workspace_nested_project():
    project = _make_project()
    ws = Workspace(project=project, media_root="/media", workspace_root="/workspace")
    assert isinstance(ws.project, VideoProject)
    assert ws.project.title == "Test Project"


def test_workspace_nested_project_enum_flattened():
    project = _make_project()
    ws = Workspace(project=project, media_root="/media", workspace_root="/workspace")
    assert isinstance(ws.project.status, str)
    assert ws.project.status == "idea"


def test_workspace_media_root_string():
    project = _make_project()
    ws = Workspace(project=project, media_root="/path/to/media", workspace_root="/workspace")
    assert ws.media_root == "/path/to/media"


def test_workspace_workspace_root_string():
    project = _make_project()
    ws = Workspace(project=project, media_root="/media", workspace_root="/path/to/workspace")
    assert ws.workspace_root == "/path/to/workspace"


def test_workspace_vault_note_path():
    project = _make_project()
    ws = Workspace(
        project=project,
        media_root="/media",
        workspace_root="/workspace",
        vault_note_path="/vault/projects/test.md",
    )
    d = ws.model_dump()
    assert d["vault_note_path"] == "/vault/projects/test.md"


def test_workspace_config_dict():
    project = _make_project()
    ws = Workspace(
        project=project,
        media_root="/media",
        workspace_root="/workspace",
        config={"proxy_quality": "720p", "auto_transcript": True},
    )
    ws2 = Workspace.from_json(ws.to_json())
    assert ws2.config["proxy_quality"] == "720p"
    assert ws2.config["auto_transcript"] is True


def test_workspace_model_dump():
    project = _make_project()
    ws = Workspace(project=project, media_root="/media", workspace_root="/workspace")
    d = ws.model_dump()
    assert "project" in d
    assert isinstance(d["project"], dict)
    assert d["project"]["title"] == "Test Project"


def test_workspace_json_round_trip():
    project = _make_project(slug="test-project", status="editing")
    ws = Workspace(
        project=project,
        media_root="/media",
        workspace_root="/workspace",
        vault_note_path="/vault/test.md",
    )
    ws2 = Workspace.from_json(ws.to_json())
    assert ws2 == ws
    assert ws2.project.slug == "test-project"


def test_workspace_yaml_round_trip():
    project = _make_project()
    ws = Workspace(
        project=project,
        media_root="/media",
        workspace_root="/workspace",
        config={"key": "value"},
    )
    ws2 = Workspace.from_yaml(ws.to_yaml())
    assert ws2 == ws


def test_workspace_invalid_project():
    # Dict without required 'title' field should raise ValidationError
    with pytest.raises(ValidationError):
        Workspace(
            project={"slug": "no-title"},  # type: ignore[arg-type]
            media_root="/media",
            workspace_root="/workspace",
        )


def test_workspace_project_accepts_dict_coercion():
    # Valid dict with title is coerced to VideoProject by Pydantic v2
    ws = Workspace(
        project={"title": "My Project"},  # type: ignore[arg-type]
        media_root="/media",
        workspace_root="/workspace",
    )
    assert isinstance(ws.project, VideoProject)
    assert ws.project.title == "My Project"


def test_workspace_mutable_default_isolation():
    project = _make_project()
    ws1 = Workspace(project=project, media_root="/m", workspace_root="/w")
    ws2 = Workspace(project=project, media_root="/m", workspace_root="/w")
    ws1.config["key"] = "value"
    assert "key" not in ws2.config
