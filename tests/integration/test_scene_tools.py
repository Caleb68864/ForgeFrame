"""media_split_scenes on a real hard cut, with both engines."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from tests._testkit import call_tool, make_hard_cut_clip, requires_ffmpeg_ffprobe, requires_scenedetect
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import count_audio_streams, probe_media
from workshop_video_brain.edit_mcp.server.bundles.media_split_scenes import media_split_scenes

pytestmark = requires_ffmpeg_ffprobe


def _first_frame_mean(video: Path, tmp_path: Path) -> list[float]:
    png = tmp_path / f"{video.stem}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-frames:v", "1", str(png)],
        check=True, timeout=60,
    )
    with Image.open(png) as image:
        return ImageStat.Stat(image.convert("RGB")).mean


def _assert_split(tmp_path: Path, engine: str) -> None:
    clip = make_hard_cut_clip(tmp_path / "cut.mp4", with_audio=True)
    result = call_tool(media_split_scenes, str(clip), str(tmp_path / "shots"), engine=engine)
    assert result["status"] == "success", result
    data = result["data"]
    assert data["engine"] == engine
    assert data["shot_count"] == 2
    paths = [Path(shot["path"]) for shot in data["shots"]]
    for path in paths:
        assert abs(probe_media(path).duration - 2.0) <= 0.1
    assert count_audio_streams(paths[1]) == 1
    red, _green, blue = _first_frame_mean(paths[1], tmp_path)
    assert blue > 150 and red < 80, f"shot 2 should open blue, mean R={red} B={blue}"


def test_split_with_ffmpeg(tmp_path):
    _assert_split(tmp_path, "ffmpeg")


@requires_scenedetect
def test_split_with_pyscenedetect(tmp_path):
    _assert_split(tmp_path, "pyscenedetect")


def test_stream_copy_keeps_the_source_container(tmp_path):
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    result = call_tool(media_split_scenes, str(clip), str(tmp_path / "shots"), engine="ffmpeg", reencode=False)
    assert result["status"] == "success", result
    assert all(Path(shot["path"]).is_file() for shot in result["data"]["shots"])


def test_file_without_video_is_unreadable(tmp_path):
    from tests._testkit import make_test_clip

    tone = make_test_clip(tmp_path / "tone.wav", kind="tone")
    result = call_tool(media_split_scenes, str(tone), str(tmp_path / "shots"), engine="ffmpeg")
    assert result["error_type"] == "media_unreadable"
    assert not (tmp_path / "shots").exists()


def test_garbage_source_is_unreadable(tmp_path):
    garbage = tmp_path / "garbage.mp4"
    garbage.write_bytes(bytes(range(256)) * 4)
    result = call_tool(media_split_scenes, str(garbage), str(tmp_path / "shots"), engine="ffmpeg")
    assert result["error_type"] == "media_unreadable"


def test_failed_shot_removes_files_already_written(tmp_path, monkeypatch):
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult, run_ffmpeg
    from workshop_video_brain.edit_mcp.pipelines import scene_split

    calls = []

    def fail_on_second(args, input_path, output_path, **kwargs):
        calls.append(output_path)
        if len(calls) == 2:
            return FFmpegResult(success=False, input_path=str(input_path), output_path=str(output_path),
                                command=[], stderr="boom")
        return run_ffmpeg(args, input_path=input_path, output_path=output_path, **kwargs)

    monkeypatch.setattr(scene_split, "run_ffmpeg", fail_on_second)
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    output = tmp_path / "shots"
    result = call_tool(media_split_scenes, str(clip), str(output), engine="ffmpeg")
    assert result["error_type"] == "operation_failed"
    assert "boom" in result["message"]
    assert list(output.iterdir()) == []


@pytest.mark.parametrize("name", ["media/raw", "projects/source"])
def test_protected_output_is_refused_with_real_media(tmp_path, name):
    clip = make_hard_cut_clip(tmp_path / "cut.mp4")
    result = call_tool(media_split_scenes, str(clip), str(tmp_path / name), engine="ffmpeg")
    assert result["error_type"] == "invalid_input"
    assert not (tmp_path / name).exists()
