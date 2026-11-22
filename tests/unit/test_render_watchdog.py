"""Render stall watchdog: a melt that stops printing progress is killed (with its group) and retried once."""
from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.render import executor

# Fake melt: behaviour per call from a plan file; writes the avformat output when it "renders".
_FAKE = r'''#!{python}
import os, pathlib, subprocess, sys, time
here = pathlib.Path(__file__).parent
calls = here / "calls"
n = int(calls.read_text()) if calls.exists() else 0
calls.write_text(str(n + 1))
plan = (here / "plan").read_text().split(",")
action = plan[min(n, len(plan) - 1)]
out = next(a for a in sys.argv if a.startswith("avformat:"))[len("avformat:"):]
sys.stderr.write('mlt_repository_register: Duplicate filter registration for "frei0r.B"\n'); sys.stderr.flush()
if action == "stall":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (here / f"child_{n}").write_text(str(child.pid))
    sys.stderr.write("Current Frame:          1, percentage:          2\n"); sys.stderr.flush()
    time.sleep(60)
if action == "slow":
    for f in range(4):
        time.sleep(0.8)
        sys.stderr.write(f"Current Frame: {f}, percentage: {f * 25}\n"); sys.stderr.flush()
pathlib.Path(out).write_bytes(b"x" * 64)
'''


@pytest.fixture
def fake_melt(tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    melt = folder / "melt"
    melt.write_text(_FAKE.replace("{python}", sys.executable))
    melt.chmod(melt.stat().st_mode | stat.S_IEXEC)

    def plan(text: str):
        (folder / "plan").write_text(text)
        (folder / "calls").unlink(missing_ok=True)
        return melt
    plan.folder = folder
    plan.calls = lambda: int((folder / "calls").read_text())
    return plan


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie still answers kill(0); check its state
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except FileNotFoundError:
        return False


def test_stall_kills_the_whole_process_group(fake_melt, tmp_path):
    melt = fake_melt("stall")
    started = time.monotonic()
    with pytest.raises(executor.RenderStalled):
        executor._run_render_process([str(melt), "-progress2", f"avformat:{tmp_path / 'o.mp4'}"], 60,
                                     stall_seconds=1.5)
    assert time.monotonic() - started < 10
    child = int((fake_melt.folder / "child_0").read_text())
    time.sleep(0.3)
    assert not _alive(child), "the stalled melt's child process was orphaned"


def test_slow_but_moving_render_is_not_a_stall(fake_melt, tmp_path):
    melt = fake_melt("slow")
    result = executor._run_render_process([str(melt), "-progress2", f"avformat:{tmp_path / 'o.mp4'}"], 60,
                                          stall_seconds=2.0)
    assert result.returncode == 0 and result.stderr.count("Current Frame") == 4


def _job(tmp_path: Path):
    from workshop_video_brain.core.models.enums import JobStatus
    from workshop_video_brain.core.models.project import RenderJob

    project = tmp_path / "p.kdenlive"
    project.write_text("<mlt/>")
    output = tmp_path / "out.mp4"
    return RenderJob(workspace_id="11111111-1111-1111-1111-111111111111", project_path=str(project),
                     output_path=str(output), profile="preview", log_path=f"{output}.log", status=JobStatus.queued)


@pytest.fixture
def render_env(monkeypatch, fake_melt):
    from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

    monkeypatch.setenv("WVB_RENDER_STALL_SECONDS", "1.5")
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    monkeypatch.setattr(executor, "missing_media", lambda _p: [])
    monkeypatch.setattr(executor, "verify_render_output", lambda p, **k: (2.0, 64))
    monkeypatch.setattr(executor, "_write_melt_profile", lambda *a, **k: None)

    def use(plan: str):
        melt = fake_melt(plan)
        monkeypatch.setattr(executor, "_build_command",
                            lambda job, profile: [str(melt), "-progress2", job.project_path, "-consumer",
                                                  f"avformat:{job.output_path}"])
        return load_profile("preview")
    return use


def test_one_stall_is_retried(render_env, fake_melt, tmp_path):
    profile = render_env("stall,ok")
    done = executor.execute_render(_job(tmp_path), profile)
    assert done.status == "succeeded", done.error_message
    assert fake_melt.calls() == 2


def test_two_stalls_fail_clearly_and_clean_up(render_env, fake_melt, tmp_path):
    profile = render_env("stall")
    started = time.monotonic()
    done = executor.execute_render(_job(tmp_path), profile)
    assert time.monotonic() - started < 20
    assert done.status == "failed" and done.error_type == "render_stalled"
    assert "no progress for 2s, twice" in done.error_message or "no progress for 1s, twice" in done.error_message
    assert fake_melt.calls() == 2
    assert not (tmp_path / "out.mp4").exists()
    assert "STALLED twice" in Path(f"{tmp_path / 'out.mp4'}.log").read_text()


def test_progress_arrives_live_not_in_4kb_lumps(tmp_path):
    """A text-mode read(4096) waited for 4 KB, so a short progress line only showed up at exit."""
    script = "import sys, time; sys.stderr.write('Current Frame: 1, percentage: 5\\n'); sys.stderr.flush(); time.sleep(2)"
    started, seen = time.monotonic(), []
    executor._run_render_process([sys.executable, "-c", script], 30,
                                 lambda chunk: seen.append((time.monotonic() - started, chunk)))
    assert seen and "Current Frame" in seen[0][1]
    assert seen[0][0] < 1.5, f"first progress arrived after {seen[0][0]:.2f}s"
