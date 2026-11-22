"""ForgeFrame's own melt renders work with no display (MLT Qt module offscreen).

Without a display, melt's Qt module refuses to start, logs a warning and exits
0: a title card renders as a big "INVALID" across the middle of the frame and
the render is reported as a success. These run the product paths -- the
render pipeline and the timeline-frame grab -- with DISPLAY / WAYLAND_DISPLAY
unset and check the pixels: the lower-third text is drawn and the centre of
the frame is the background colour, not "INVALID".
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tests._testkit import requires_melt
from tests.integration.test_title_renders import _add, _base_color_project
from workshop_video_brain.edit_mcp.adapters.mlt import display, engine
from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render
from workshop_video_brain.workspace.manager import WorkspaceManager

pytestmark = requires_melt


@pytest.fixture
def headless(monkeypatch):
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "QT_QPA_PLATFORM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)


@pytest.fixture
def offscreen_ok(headless):
    probe = display.probe_qt_module()
    if not probe["ready"]:
        # An older MLT that refuses QT_QPA_PLATFORM=offscreen: renders then fail
        # loudly (test_qt_refusal_fails_the_render_loudly), they cannot draw.
        pytest.skip(f"this MLT build cannot run Qt offscreen: {probe['reason']}")


def _title_project(path: Path) -> Path:
    _base_color_project(path)
    out = _add(project_file=str(path), text="HELLO WORLD", subtitle="Render Check",
               style="lower-third", at_seconds=0.0, duration_seconds=1.2, track=None)
    assert out["status"] == "success", out
    return path


def _assert_title_drawn(png: Path) -> None:
    with Image.open(png) as image:
        luma = image.convert("L").resize((1920, 1080))
    band = list(luma.crop((200, 760, 1600, 960)).get_flattened_data())
    centre = list(luma.crop((100, 420, 1820, 660)).get_flattened_data())
    assert max(band) > 200, "no lower-third text"
    # "INVALID" is drawn white across exactly this region when Qt had no display.
    assert max(centre) < 150, "Qt module had no display: the frame says INVALID"


def test_timeline_frame_grab_draws_title_headless(tmp_path, offscreen_ok, monkeypatch):
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)  # the melt path
    project = _title_project(tmp_path / "render.kdenlive")
    result = engine.timeline_frames(project, [15], 1920, tmp_path / "frames",
                                    engine="melt", profile_size=(1920, 1080))
    _assert_title_drawn(Path(result["frames"][0]["path"]))


def test_render_pipeline_draws_title_headless(tmp_path, offscreen_ok):
    root = tmp_path / "ws"
    WorkspaceManager.create("Headless", tmp_path, workspace_root=root)
    project = _title_project(root / "projects" / "working_copies" / "render_v1.kdenlive")

    job = run_render(root, project, "preview")

    assert job.status == "succeeded", (job.error_message, job.log_path)
    frame = tmp_path / "frame.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", job.output_path, "-vf", r"select=eq(n\,15)",
         "-frames:v", "1", str(frame)],
        check=True, capture_output=True, timeout=120,
    )
    _assert_title_drawn(frame)


def test_mlt_env_only_when_headless():
    assert display.mlt_env({"DISPLAY": ":0"}) == {"DISPLAY": ":0"}
    assert display.mlt_env({"QT_QPA_PLATFORM": "xcb"}) == {"QT_QPA_PLATFORM": "xcb"}
    assert display.mlt_env({"PATH": "/bin"}) == {"PATH": "/bin", "QT_QPA_PLATFORM": "offscreen"}


def test_qt_refusal_fails_the_render_loudly(tmp_path, headless, monkeypatch):
    """An MLT build that refuses offscreen: melt exits 0, the job must still fail."""
    from workshop_video_brain.edit_mcp.adapters.render import executor

    root = tmp_path / "ws"
    WorkspaceManager.create("Headless", tmp_path, workspace_root=root)
    project = _title_project(root / "projects" / "working_copies" / "render_v1.kdenlive")

    def refusing_melt(cmd, *args, **kwargs):
        Path(cmd[cmd.index("-consumer") + 1].removeprefix("avformat:")).write_bytes(b"x" * 2048)
        return subprocess.CompletedProcess(
            cmd, 0, "", "    The MLT Qt module requires a X11 or Wayland environment.\n")

    # melt renders stream through _run_render_process (progress + stall watchdog).
    monkeypatch.setattr(executor, "_run_render_process", refusing_melt)
    job = run_render(root, project, "preview")
    assert job.status == "failed"
    assert job.error_type == "missing_dependency"
    assert "xvfb-run" in job.error_message
    assert not Path(job.output_path).exists()


def test_doctor_reports_qt_module(headless):
    from workshop_video_brain.app import doctor

    report = doctor.environment_report()
    assert report["mlt_qt"]["display"] is False
    assert report["mlt_qt"]["qt_platform"] == "offscreen"
    assert report["mlt_qt"]["ready"] is display.probe_qt_module()["ready"]
    assert report["features"]["timeline_render_qt"] is report["mlt_qt"]["ready"]
