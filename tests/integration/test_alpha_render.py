"""Integration tests for alpha (transparent-background) render profiles.

Exercises the real melt render path end-to-end: builds a minimal MLT project
(a transparent ``color`` producer), runs each alpha profile through
``execute_render``, and uses ``ffprobe`` to confirm the output actually carries
an alpha channel.

Verifies the capability from the Kdenlive tutorial "Render Video with
Transparent Background" — the "Video with alpha" render presets (Alpha MOV,
Alpha VP9, FFV1) mapped onto ForgeFrame render profiles.

These tests are skipped automatically when melt / ffmpeg / ffprobe are not
installed, so they are safe to run in CI without the MLT toolchain.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

melt_available = shutil.which("melt") is not None
ffprobe_available = shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not (melt_available and ffprobe_available),
    reason="melt and ffprobe are required for alpha render integration tests",
)

# A minimal MLT project (== .kdenlive XML) with a fully-transparent color
# producer. melt reads it directly; a small frame count keeps the render fast.
_MINI_MLT = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.0.0" root="{root}" title="alpha-test">
  <profile description="VGA" width="320" height="240" progressive="1"
    sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="4"
    display_aspect_den="3" frame_rate_num="30" frame_rate_den="1"
    colorspace="601"/>
  <producer id="producer0" in="0" out="5">
    <property name="length">15000</property>
    <property name="eof">pause</property>
    <property name="resource">#00000000</property>
    <property name="aspect_ratio">1</property>
    <property name="mlt_service">color</property>
  </producer>
  <playlist id="playlist0">
    <entry producer="producer0" in="0" out="5"/>
  </playlist>
  <tractor id="tractor0" title="alpha-test" in="0" out="5">
    <track producer="playlist0"/>
  </tractor>
</mlt>
"""


def _probe_pix_fmt(path: Path) -> str:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout.strip()


def _probe_alpha_mode(path: Path) -> str:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream_tags=alpha_mode",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    return out.stdout.strip()


@pytest.fixture
def mini_project(tmp_path: Path) -> Path:
    project = tmp_path / "alpha_test.kdenlive"
    project.write_text(_MINI_MLT.format(root=tmp_path), encoding="utf-8")
    return project


def _render(profile_name: str, ext: str, project: Path, tmp_path: Path) -> Path:
    out = tmp_path / f"out_{profile_name}.{ext}"
    job = RenderJob(
        workspace_id=uuid4(),
        project_path=str(project),
        output_path=str(out),
        log_path=str(tmp_path / f"{profile_name}.log"),
    )
    profile = load_profile(profile_name)
    result = execute_render(job, profile)
    assert result.status in ("succeeded", "succeeded"), (
        f"{profile_name} render did not succeed: {result.status}\n"
        f"log: {Path(job.log_path).read_text() if Path(job.log_path).exists() else '(none)'}"
    )
    assert out.exists() and out.stat().st_size > 0
    return out


class TestAlphaRenderProfilesProduceAlpha:
    def test_webm_alpha_carries_alpha(self, mini_project, tmp_path):
        out = _render("webm-alpha", "webm", mini_project, tmp_path)
        probe = _probe_pix_fmt(out)
        assert probe.startswith("vp9"), probe
        # VP9/WebM stores alpha as a hidden secondary stream flagged by the
        # container tag alpha_mode=1 (the primary stream reports yuv420p).
        assert _probe_alpha_mode(out) == "1"

    def test_prores_4444_alpha_carries_alpha(self, mini_project, tmp_path):
        out = _render("prores-4444-alpha", "mov", mini_project, tmp_path)
        probe = _probe_pix_fmt(out)
        assert probe.startswith("prores"), probe
        # ProRes 4444 encodes alpha directly in a yuva444p pixel format.
        assert "yuva444" in probe, probe

    def test_mov_alpha_carries_alpha(self, mini_project, tmp_path):
        out = _render("mov-alpha", "mov", mini_project, tmp_path)
        probe = _probe_pix_fmt(out)
        assert probe.startswith("qtrle"), probe
        assert "argb" in probe, probe

    def test_ffv1_alpha_carries_alpha(self, mini_project, tmp_path):
        out = _render("ffv1-alpha", "mkv", mini_project, tmp_path)
        probe = _probe_pix_fmt(out)
        assert probe.startswith("ffv1"), probe
        assert "yuva420p" in probe, probe
