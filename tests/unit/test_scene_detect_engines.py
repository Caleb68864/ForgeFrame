"""Engine selection and dispatch; needs neither scenedetect nor ffmpeg."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg import scene as ffmpeg_scene
from workshop_video_brain.edit_mcp.adapters.scenedetect import engine as adapter
from workshop_video_brain.edit_mcp.pipelines import scene_detect
from workshop_video_brain.edit_mcp.pipelines.scene_detect import (
    EngineUnavailable,
    SceneDetectError,
    detect_scenes,
    resolve_engine,
    scan_cuts,
)


def _set_installed(monkeypatch, installed: bool) -> None:
    monkeypatch.setattr(adapter, "is_available", lambda: installed)


def test_auto_prefers_pyscenedetect_when_installed(monkeypatch):
    _set_installed(monkeypatch, True)
    assert resolve_engine("auto") == "pyscenedetect"


def test_auto_falls_back_to_ffmpeg_when_absent(monkeypatch):
    _set_installed(monkeypatch, False)
    assert resolve_engine("auto") == "ffmpeg"


def test_unknown_engine_raises_value_error():
    with pytest.raises(ValueError, match="Unknown engine 'nope'"):
        resolve_engine("nope")


def test_unknown_detector_raises_value_error():
    with pytest.raises(ValueError, match="Unknown detector 'nope'"):
        scan_cuts(Path("x.mp4"), detector="nope")


def test_missing_package_raises_with_install_hint(monkeypatch):
    _set_installed(monkeypatch, False)
    with pytest.raises(EngineUnavailable, match=r"scene-detect"):
        resolve_engine("pyscenedetect")


def test_import_failure_after_resolving_still_reports_engine_unavailable(monkeypatch):
    """find_spec can succeed for a package whose import then fails."""
    _set_installed(monkeypatch, True)

    def broken(_module):
        raise ImportError("libsomething.so missing")

    monkeypatch.setattr(adapter.importlib, "import_module", broken)
    with pytest.raises(EngineUnavailable, match=r"scene-detect"):
        scan_cuts(Path("x.mp4"), engine="pyscenedetect")


def test_dispatch_passes_detector_args_through(monkeypatch):
    _set_installed(monkeypatch, True)
    seen = {}

    def fake(path, **kwargs):
        seen.update(kwargs, path=path)
        return [(2.0, 0.5)]

    monkeypatch.setattr(adapter, "scan_cuts", fake)
    result = scan_cuts(Path("x.mp4"), engine="pyscenedetect", detector="adaptive", detector_threshold=5.0)
    assert result == ("pyscenedetect", [(2.0, 0.5)])
    assert seen["path"] == Path("x.mp4")
    assert seen["detector"] == "adaptive"
    assert seen["detector_threshold"] == 5.0


def test_ffmpeg_dispatch_uses_threshold_and_range(monkeypatch):
    calls = []

    def spy(path, threshold, start, end):
        calls.append((path, threshold, start, end))
        return [(1.0, 0.9)]

    monkeypatch.setattr(scene_detect, "scan_scene_cuts", spy)
    assert scan_cuts(Path("x.mp4"), threshold=0.7, start_seconds=1.0, end_seconds=3.0) == ("ffmpeg", [(1.0, 0.9)])
    assert calls == [(Path("x.mp4"), 0.7, 1.0, 3.0)]


def test_detect_scenes_unreadable_is_not_a_zero_cut_success(monkeypatch):
    _set_installed(monkeypatch, True)

    def bad(*_args, **_kwargs):
        raise SceneDetectError("cannot decode")

    monkeypatch.setattr(adapter, "scan_cuts", bad)
    result = detect_scenes(Path("x.mp4"), engine="pyscenedetect")
    assert result["success"] is False
    assert result["error_type"] == "media_unreadable"
    assert "cuts" not in result


def test_detect_scenes_missing_engine_is_missing_dependency(monkeypatch):
    _set_installed(monkeypatch, False)
    result = detect_scenes(Path("x.mp4"), engine="pyscenedetect")
    assert result["success"] is False
    assert result["error_type"] == "missing_dependency"
    assert "scene-detect" in result["error"]


def test_detect_scenes_default_stays_on_ffmpeg(monkeypatch):
    _set_installed(monkeypatch, True)
    calls = []

    def spy(path, threshold, start, end):
        calls.append(path)
        return [(2.0, 0.8)]

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the default engine must not change")

    monkeypatch.setattr(scene_detect, "scan_scene_cuts", spy)
    monkeypatch.setattr(adapter, "scan_cuts", forbidden)
    result = detect_scenes(Path("x.mp4"))
    assert calls == [Path("x.mp4")]
    assert result["engine"] == "ffmpeg"
    assert result["cuts"] == [{"time": 2.0, "score": 0.8}]


def test_dry_run_reports_engine_and_no_command_for_pyscenedetect(monkeypatch):
    _set_installed(monkeypatch, True)
    result = detect_scenes(Path("x.mp4"), dry_run=True, engine="pyscenedetect")
    assert result["success"] is True
    assert result["engine"] == "pyscenedetect"
    assert result["command"] is None


def test_detect_scene_changes_uses_injected_scan(monkeypatch):
    class Asset:
        duration_seconds = 10.0

    monkeypatch.setattr(ffmpeg_scene, "probe_media", lambda _path: Asset())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the injected scan must replace the ffmpeg one")

    monkeypatch.setattr(ffmpeg_scene, "scan_scene_cuts", forbidden)
    seen = []

    def fake(path, threshold, start, end):
        seen.append((path, threshold, start, end))
        return [(4.0, 0.6)]

    changes = ffmpeg_scene.detect_scene_changes(Path("x.mp4"), threshold=0.25, scan=fake)
    assert seen == [(Path("x.mp4"), 0.25, 0.0, 10.0)]
    assert [(c.timestamp_seconds, c.score) for c in changes] == [(4.0, 0.6)]
