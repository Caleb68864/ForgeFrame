"""Progress reaches the job record, throttled; no real render."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.mlt import engine
from workshop_video_brain.edit_mcp.adapters.render import executor
from workshop_video_brain.edit_mcp.adapters.render.progress import RenderProgress, Throttle


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def _update(percent: float) -> RenderProgress:
    return RenderProgress(frame=int(percent), total_frames=100, percent=percent, engine="mlt")


def test_throttle_forwards_first_then_only_on_change_or_time():
    seen = []
    clock = Clock()
    throttled = Throttle(seen.append, clock=clock)
    throttled(_update(0.0))
    throttled(_update(0.5))  # same second, under 1 percent: dropped
    assert [u.percent for u in seen] == [0.0]
    throttled(_update(1.5))  # moved by 1 percent
    assert [u.percent for u in seen] == [0.0, 1.5]
    throttled(_update(1.6))  # dropped
    clock.now = 1.5
    throttled(_update(1.7))  # a second has passed
    assert [u.percent for u in seen] == [0.0, 1.5, 1.7]


def test_throttle_always_forwards_the_final_update():
    seen = []
    throttled = Throttle(seen.append, clock=Clock())
    throttled(_update(99.5))
    throttled(_update(100.0))
    assert [u.percent for u in seen] == [99.5, 100.0]


def _job(tmp_path: Path):
    from workshop_video_brain.core.models.enums import JobStatus
    from workshop_video_brain.core.models.project import RenderJob

    project = tmp_path / "p.kdenlive"
    project.write_text("<mlt/>")
    output = tmp_path / "out.mp4"
    return RenderJob(workspace_id="11111111-1111-1111-1111-111111111111", project_path=str(project),
                     output_path=str(output), profile="preview", log_path=f"{output}.log",
                     status=JobStatus.queued)


def _profile():
    from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

    return load_profile("preview")


@pytest.mark.parametrize("variable", ["mlt", "auto"])
def test_bindings_engine_streams_progress(tmp_path, monkeypatch, variable):
    worker = tmp_path / "fake_worker.py"
    worker.write_text(
        "import json, sys\nrequest = json.loads(sys.stdin.readline())\n"
        "open(request['args']['out'], 'wb').write(b'x')\n"
        "for f in (10, 20, 49):\n"
        "    print(json.dumps({'event': 'progress', 'frame': f, 'total': 50}), flush=True)\n"
        "print(json.dumps({'ok': True, 'result': {}}))\n"
    )
    real = engine.run_streaming_worker

    def run(op, args, **kwargs):
        return real(op, args, _interpreter=sys.executable, _worker_path=worker, **kwargs)

    monkeypatch.setenv("WVB_RENDER_ENGINE", variable)
    monkeypatch.setattr(engine, "run_streaming_worker", run)
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: object())
    monkeypatch.setattr(executor, "missing_media", lambda _p: [])
    monkeypatch.setattr(executor, "verify_render_output", lambda _p: (2.0, 1))
    seen = []
    done = executor.execute_render(_job(tmp_path), _profile(), on_progress=seen.append)
    assert done.status == "succeeded", done.error_message
    assert [u.frame for u in seen] == [10, 20, 49]
    assert {u.engine for u in seen} == {"mlt"}
    assert seen[-1].percent == 100.0
    assert "Return code: 0" in Path(done.log_path).read_text()


def test_default_engine_is_still_melt(monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: object())
    assert executor._select_render_engine(Path("p.kdenlive")) == "melt"


def test_auto_without_bindings_is_melt(monkeypatch):
    monkeypatch.setenv("WVB_RENDER_ENGINE", "auto")
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: None)
    assert executor._select_render_engine(Path("p.kdenlive")) == "melt"


def test_non_project_input_never_uses_bindings(monkeypatch):
    monkeypatch.setenv("WVB_RENDER_ENGINE", "mlt")
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: object())
    assert executor._select_render_engine(Path("clip.mp4")) == "melt"


def test_consumer_props_match_the_melt_command():
    props = executor._melt_consumer_props(["melt", "p.kdenlive", "-consumer", "avformat:o.mp4", "vcodec=libx264", "vb=2M"])
    assert props == {"vcodec": "libx264", "vb": "2M"}


def test_worker_crash_fails_the_job_and_removes_partial_output(tmp_path, monkeypatch):
    def crash(*_a, **_k):
        raise engine.MltWorkerCrashed("SIGSEGV")

    monkeypatch.setenv("WVB_RENDER_ENGINE", "mlt")
    monkeypatch.setattr(engine, "find_mlt_python", lambda **_k: object())
    monkeypatch.setattr(engine, "run_streaming_worker", crash)
    monkeypatch.setattr(executor, "missing_media", lambda _p: [])
    job = _job(tmp_path)
    Path(job.output_path).unlink(missing_ok=True)
    done = executor.execute_render(job, _profile())
    assert done.status == "failed"
    assert "SIGSEGV" in done.error_message
    assert not Path(job.output_path).exists()
