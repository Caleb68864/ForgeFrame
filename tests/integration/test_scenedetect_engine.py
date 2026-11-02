"""PySceneDetect against real synthetic cuts, cross-checked with ffmpeg."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import _run_ffmpeg, make_hard_cut_clip, make_test_clip, requires_ffmpeg_ffprobe, requires_scenedetect
from workshop_video_brain.edit_mcp.adapters.scenedetect.engine import SceneDetectError
from workshop_video_brain.edit_mcp.pipelines.scene_detect import resolve_engine, scan_cuts

pytestmark = [requires_scenedetect, requires_ffmpeg_ffprobe]

FRAME = 0.04


@pytest.fixture(scope="module")
def cut_clip(tmp_path_factory) -> Path:
    return make_hard_cut_clip(tmp_path_factory.mktemp("cut") / "cut.mp4")


def test_auto_resolves_to_pyscenedetect_when_installed():
    assert resolve_engine("auto") == "pyscenedetect"


@pytest.mark.parametrize("detector", ["content", "adaptive"])
def test_detector_finds_the_one_cut(cut_clip, detector):
    engine, hits = scan_cuts(cut_clip, engine="pyscenedetect", detector=detector)
    assert engine == "pyscenedetect"
    assert len(hits) == 1
    time, score = hits[0]
    assert abs(time - 2.0) <= FRAME
    assert 0.0 < score <= 1.0


def test_threshold_detector_sees_no_cut_between_two_bright_colours(cut_clip):
    """ThresholdDetector looks for fades through black; red-to-blue never crosses its floor."""
    _engine, hits = scan_cuts(cut_clip, engine="pyscenedetect", detector="threshold")
    assert hits == []


def test_threshold_detector_finds_a_cut_through_black(tmp_path):
    """White, 2 s of black, white: the scene boundary falls inside the black span."""
    clip = tmp_path / "black.mp4"
    args = []
    for color in ("white", "black", "white"):
        args += ["-f", "lavfi", "-i", f"color=c={color}:size=320x240:rate=25:duration=2"]
    _run_ffmpeg([*args, "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                 "-pix_fmt", "yuv420p", str(clip)])
    _engine, hits = scan_cuts(clip, engine="pyscenedetect", detector="threshold")
    assert len(hits) == 1
    time, score = hits[0]
    assert 2.0 <= time <= 4.0
    assert 0.0 <= score <= 1.0


def test_engines_agree_on_the_cut(cut_clip):
    _engine, ffmpeg_hits = scan_cuts(cut_clip, engine="ffmpeg", threshold=0.4)
    _engine, scenedetect_hits = scan_cuts(cut_clip, engine="pyscenedetect")
    assert len(ffmpeg_hits) == len(scenedetect_hits) == 1
    assert abs(ffmpeg_hits[0][0] - scenedetect_hits[0][0]) <= FRAME


def test_range_limits_keep_absolute_times(cut_clip):
    _engine, hits = scan_cuts(cut_clip, engine="pyscenedetect", min_scene_seconds=0.2,
                              start_seconds=1.0, end_seconds=3.0)
    assert [round(time, 2) for time, _score in hits] == [2.0]
    _engine, outside = scan_cuts(cut_clip, engine="pyscenedetect", min_scene_seconds=0.2, start_seconds=2.5)
    assert outside == []


def test_native_threshold_reaches_the_detector(cut_clip):
    _engine, hits = scan_cuts(cut_clip, engine="pyscenedetect", detector_threshold=200.0)
    assert hits == []


def test_clip_without_cuts_gives_none(tmp_path):
    clip = make_test_clip(tmp_path / "flat.mp4", kind="color")
    assert scan_cuts(clip, engine="pyscenedetect") == ("pyscenedetect", [])


def test_garbage_file_raises(tmp_path):
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(SceneDetectError):
        scan_cuts(garbage, engine="pyscenedetect")
