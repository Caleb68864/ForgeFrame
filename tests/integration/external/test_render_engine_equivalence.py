"""The render path against the opt-in bindings engine, and against melt's own render.

Before ``-profile``, the default path rendered through melt's default profile: black
pillars and shifted colours (22 dB against the correct picture), and a hang outright
for a project that is not 25 fps. Both are pinned here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests._testkit import make_test_clip, requires_melt_ffmpeg, requires_mlt_bindings, sequence_project
from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

pytestmark = [pytest.mark.external, requires_melt_ffmpeg, requires_mlt_bindings]


def _render(project: Path, output: Path, engine: str, monkeypatch, **kwargs):
    monkeypatch.setenv("WVB_RENDER_ENGINE", engine)
    job = RenderJob(workspace_id="11111111-1111-1111-1111-111111111111", project_path=str(project),
                    output_path=str(output), profile="preview", log_path=f"{output}.log",
                    status=JobStatus.queued)
    done = execute_render(job, load_profile("preview"), **kwargs)
    assert done.status == "succeeded", done.error_message
    return output


def _frames(path: Path) -> int:
    return int(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout.strip().rstrip(","))


def _psnr(a: Path, b: Path) -> float:
    stderr = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "psnr", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    ).stderr
    value = re.search(r"average:(inf|[\d.]+)", stderr).group(1)
    return float("inf") if value == "inf" else float(value)


def _plain_melt(project: Path, output: Path) -> Path:
    subprocess.run(
        ["melt", str(project), "-consumer", f"avformat:{output}", "vcodec=libx264", "vb=2M", "acodec=aac", "ab=128k",
         "terminate_on_pause=1"],
        check=True, capture_output=True, timeout=180,
    )
    return output


@pytest.fixture
def color_project(tmp_path) -> Path:
    project = tmp_path / "color.kdenlive"
    serialize_project(sequence_project(width=1280, height=720), project)
    return project


@pytest.fixture
def media_project(tmp_path) -> Path:
    clip = make_test_clip(tmp_path / "clip.mp4", duration=2, with_audio=True, size=(1280, 720))
    built = sequence_project(width=1280, height=720)
    built.producers[0].resource = str(clip)
    built.producers[0].properties = {"resource": str(clip), "mlt_service": "avformat", "length": "50"}
    project = tmp_path / "media.kdenlive"
    serialize_project(built, project)
    return project


@pytest.mark.parametrize("project_fixture", ["color_project", "media_project"])
def test_bindings_match_melt_at_the_project_profile(project_fixture, request, tmp_path, monkeypatch):
    project = request.getfixturevalue(project_fixture)
    melt = _plain_melt(project, tmp_path / "melt.mp4")
    updates = []
    mlt = _render(project, tmp_path / "mlt.mp4", "mlt", monkeypatch, on_progress=updates.append)
    assert _frames(melt) == _frames(mlt)
    assert _psnr(melt, mlt) >= 40
    frames = [update.frame for update in updates]
    assert len(frames) >= 2
    assert frames == sorted(frames)


def test_default_render_path_matches_the_bindings(color_project, tmp_path, monkeypatch):
    melt = _render(color_project, tmp_path / "melt.mp4", "melt", monkeypatch)
    mlt = _render(color_project, tmp_path / "mlt.mp4", "mlt", monkeypatch)
    assert _psnr(melt, mlt) >= 40


def test_default_render_path_is_not_pillarboxed(tmp_path, monkeypatch):
    project = tmp_path / "small.kdenlive"
    serialize_project(sequence_project(width=320, height=180), project)  # scaled to the profile's 1280x720
    output = _render(project, tmp_path / "out.mp4", "melt", monkeypatch)
    png = tmp_path / "edge.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.2", "-i", str(output), "-frames:v", "1", str(png)],
                   check=True, timeout=60)
    from PIL import Image

    with Image.open(png) as image:
        rgb = image.convert("RGB")
        assert rgb.size == (1280, 720)
        red, _green, _blue = rgb.getpixel((2, 360))
    assert red > 200, "the left edge of the frame is a black pillar"


def test_ntsc_real_media_project_renders_instead_of_hanging(tmp_path, monkeypatch):
    fixture = Path(__file__).parents[2] / "fixtures/media_generated/test_clip_1080p2997_5s.mp4"
    built = sequence_project(width=1920, height=1080, fps=30000 / 1001, frames_each=60)
    built.producers[0].resource = str(fixture)
    built.producers[0].properties = {"resource": str(fixture), "mlt_service": "avformat", "length": "149"}
    project = tmp_path / "ntsc.kdenlive"
    serialize_project(built, project)
    output = _render(project, tmp_path / "out.mp4", "melt", monkeypatch, timeout_seconds=90)
    assert _frames(output) >= 60
