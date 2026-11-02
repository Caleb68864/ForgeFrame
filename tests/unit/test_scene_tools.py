"""Tool contracts for the scene engines, with the scanners faked."""
from __future__ import annotations

import importlib
import inspect

import pytest

from tests._testkit import assert_registered, call_tool, unwrap
from workshop_video_brain.edit_mcp.adapters.scenedetect import engine as adapter
from workshop_video_brain.edit_mcp.pipelines import scene_detect
from workshop_video_brain.edit_mcp.server.bundles import media_split_scenes as split_module
from workshop_video_brain.edit_mcp.server.bundles import scene_detect as clips_module
from workshop_video_brain.edit_mcp.server.tools import research_media
from workshop_video_brain.workspace.manager import WorkspaceManager


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"not decoded: the scanners are faked")
    return path


def test_tools_are_registered():
    importlib.import_module("workshop_video_brain.edit_mcp.server.bundles.scene_guides")
    assert_registered("media_split_scenes", "guide_add_scene_cuts")


@pytest.mark.parametrize("tool", [clips_module.clips_detect_scenes, research_media.research_detect_scenes])
def test_existing_tools_keep_ffmpeg_as_the_default(tool):
    parameters = inspect.signature(unwrap(tool)).parameters
    assert parameters["engine"].default == "ffmpeg"
    assert list(parameters)[-3:] == ["engine", "detector", "detector_threshold"]


def test_split_refuses_empty_output_dir(media):
    result = call_tool(split_module.media_split_scenes, str(media), "  ")
    assert result["error_type"] == "invalid_input"
    assert "outside media/raw" in result["suggestion"]


def test_split_refuses_a_protected_output_dir(media, tmp_path, monkeypatch):
    class Asset:
        video_codec, audio_codec, duration = "h264", "", 4.0

    monkeypatch.setattr("workshop_video_brain.edit_mcp.pipelines.scene_split.probe_media", lambda _p: Asset())
    monkeypatch.setattr(scene_detect, "scan_scene_cuts", lambda *_a: [])
    protected = tmp_path / "media" / "raw"
    result = call_tool(split_module.media_split_scenes, str(media), str(protected), engine="ffmpeg")
    assert result["error_type"] == "invalid_input"
    assert not protected.exists()


def test_split_refuses_an_unknown_engine(media, tmp_path):
    result = call_tool(split_module.media_split_scenes, str(media), str(tmp_path / "out"), engine="nope")
    assert result["error_type"] == "invalid_input"


def test_split_refuses_nonpositive_min_shot(media, tmp_path):
    result = call_tool(split_module.media_split_scenes, str(media), str(tmp_path / "out"),
                       engine="ffmpeg", min_shot_seconds=0)
    assert result["error_type"] == "invalid_input"


def test_split_missing_source(tmp_path):
    result = call_tool(split_module.media_split_scenes, str(tmp_path / "gone.mp4"), str(tmp_path / "out"))
    assert result["error_type"] == "missing_file"


def test_research_missing_package_is_missing_dependency(media, monkeypatch):
    monkeypatch.setattr(adapter, "is_available", lambda: False)
    result = call_tool(research_media.research_detect_scenes, str(media), engine="pyscenedetect")
    assert result["error_type"] == "missing_dependency"
    assert "scene-detect" in result["suggestion"]


def test_research_unknown_engine_is_invalid_input(media):
    result = call_tool(research_media.research_detect_scenes, str(media), engine="nope")
    assert result["error_type"] == "invalid_input"


def test_research_reports_engine_and_unreadable_media(media, monkeypatch):
    monkeypatch.setattr(adapter, "is_available", lambda: True)

    def bad(*_args, **_kwargs):
        raise adapter.SceneDetectError("cannot decode")

    monkeypatch.setattr(adapter, "scan_cuts", bad)
    monkeypatch.setattr("workshop_video_brain.edit_mcp.adapters.ffmpeg.scene.probe_media",
                        lambda _p: type("Asset", (), {"duration_seconds": 4.0})())
    result = call_tool(research_media.research_detect_scenes, str(media), engine="pyscenedetect")
    assert result["error_type"] == "media_unreadable"

    monkeypatch.setattr(adapter, "scan_cuts", lambda *_a, **_k: [(2.0, 0.5)])
    result = call_tool(research_media.research_detect_scenes, str(media), engine="pyscenedetect")
    assert result["status"] == "success"
    assert result["data"]["engine"] == "pyscenedetect"
    assert result["data"]["scenes"][0]["timestamp_seconds"] == 2.0


def test_clips_detect_report_includes_engine(tmp_path, media, monkeypatch):
    workspace = tmp_path / "ws"
    WorkspaceManager.create("Scenes", tmp_path, workspace_root=workspace)
    monkeypatch.setattr(scene_detect, "scan_scene_cuts", lambda *_a: [(2.0, 0.4)])
    result = call_tool(clips_module.clips_detect_scenes, str(workspace), str(media))
    assert result["status"] == "success"
    assert result["data"]["engine"] == "ffmpeg"


def test_clips_detect_missing_package_and_unknown_engine(tmp_path, media, monkeypatch):
    workspace = tmp_path / "ws"
    WorkspaceManager.create("Scenes", tmp_path, workspace_root=workspace)
    monkeypatch.setattr(adapter, "is_available", lambda: False)
    result = call_tool(clips_module.clips_detect_scenes, str(workspace), str(media), engine="pyscenedetect")
    assert result["error_type"] == "missing_dependency"
    result = call_tool(clips_module.clips_detect_scenes, str(workspace), str(media), engine="nope")
    assert result["error_type"] == "invalid_input"


def test_candidates_honour_scene_config(tmp_path, monkeypatch):
    """generate_candidates used to ignore the configured threshold and gap."""
    from workshop_video_brain.core.models.media import MediaAsset
    from workshop_video_brain.core.models.visual_research import FrameCandidate, ResearchConfig, ResearchRegion
    from workshop_video_brain.edit_mcp.pipelines.visual_research import candidates

    seen = {}

    def fake_detect(_path, **kwargs):
        seen.update(kwargs)
        return []

    source = MediaAsset(path=str(tmp_path / "video.mp4"))

    def fake_frame(_path, seconds, **_kwargs):
        return FrameCandidate(source_id=source.id, image_path=str(tmp_path / "frame.jpg"),
                              timestamp_seconds=seconds, width=4, height=4)

    monkeypatch.setattr(candidates, "detect_scene_changes", fake_detect)
    monkeypatch.setattr(candidates, "extract_frame", fake_frame)
    monkeypatch.setattr(candidates, "extract_frame_burst", lambda *_a, **_k: [])
    monkeypatch.setattr(candidates, "_probe_once", lambda _path, asset: asset)
    config = ResearchConfig()
    config.scene_detection.threshold = 0.77
    config.scene_detection.min_scene_length_seconds = 3.5

    candidates.generate_candidates(
        tmp_path / "video.mp4",
        ResearchRegion(source_id=source.id, start_seconds=0.0, end_seconds=4.0),
        source,
        config,
        output_dir=tmp_path,
    )
    assert seen["threshold"] == 0.77
    assert seen["minimum_gap_seconds"] == 3.5
    assert seen["scan"] is None
