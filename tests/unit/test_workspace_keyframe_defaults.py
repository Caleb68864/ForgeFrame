"""Tests for Workspace keyframe_defaults round-trip and validation."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest


def _patch_yaml_ease_family(ws_root: Path, family: str) -> None:
    path = ws_root / "workspace.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["keyframe_defaults"] = {"ease_family": family}
    path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")


def test_loads_ease_family_from_yaml(tmp_path: Path):
    ws_root = tmp_path / "proj"
    WorkspaceManager.create("P", media_root=tmp_path / "media", workspace_root=ws_root)
    _patch_yaml_ease_family(ws_root, "expo")
    ws = WorkspaceManager.open(ws_root)
    assert ws.keyframe_defaults.ease_family == "expo"


def test_missing_keyframe_defaults_yields_cubic(tmp_path: Path):
    ws_root = tmp_path / "proj"
    WorkspaceManager.create("P", media_root=tmp_path / "media", workspace_root=ws_root)
    # Strip the key entirely
    path = ws_root / "workspace.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("keyframe_defaults", None)
    path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

    ws = WorkspaceManager.open(ws_root)
    assert ws.keyframe_defaults.ease_family == "cubic"


def test_invalid_ease_family_raises_validation_error(tmp_path: Path):
    ws_root = tmp_path / "proj"
    WorkspaceManager.create("P", media_root=tmp_path / "media", workspace_root=ws_root)
    _patch_yaml_ease_family(ws_root, "not-a-family")
    with pytest.raises(ValidationError):
        WorkspaceManager.open(ws_root)


def test_roundtrip_ease_family_through_save_load(tmp_path: Path):
    ws_root = tmp_path / "proj"
    ws = WorkspaceManager.create("P", media_root=tmp_path / "media", workspace_root=ws_root)
    ws.keyframe_defaults.ease_family = "bounce"
    WorkspaceManager.save_manifest(ws)

    # Manifest persists the value
    manifest = read_manifest(ws_root)
    assert manifest.keyframe_defaults.ease_family == "bounce"

    # Full reopen restores it on the Workspace
    reopened = WorkspaceManager.open(ws_root)
    assert reopened.keyframe_defaults.ease_family == "bounce"
