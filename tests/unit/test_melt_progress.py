"""melt CLI render progress and stricter post-render verification (prompt 18)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from workshop_video_brain.edit_mcp.adapters.render import executor
from workshop_video_brain.edit_mcp.adapters.render.progress import (
    MeltProgressReader,
    parse_melt_progress,
)

SAMPLE = "Current Frame:         31, percentage:         62"
NOISE = "mlt_repository_register: Duplicate filter registration for \"frei0r.B\"\n"


# ---------------------------------------------------------------------------
# parse_melt_progress / MeltProgressReader
# ---------------------------------------------------------------------------

def test_exact_sample():
    assert parse_melt_progress(SAMPLE) == [(31, 62)]


def test_carriage_return_stream():
    chunk = "Current Frame:  10, percentage:  20\rCurrent Frame:  20, percentage:  40\r"
    assert parse_melt_progress(chunk) == [(10, 20), (20, 40)]


def test_newline_stream_with_noise():
    chunk = NOISE + "Current Frame: 5, percentage: 10\n" + NOISE * 3 + "Current Frame: 9, percentage: 18\n"
    assert parse_melt_progress(chunk) == [(5, 10), (9, 18)]


def test_reader_joins_a_line_split_across_chunks():
    seen = []
    reader = MeltProgressReader(seen.append, total_frames=50)
    reader.feed(NOISE + "Current Frame:   2")
    assert seen == []
    reader.feed("9, percentage:   58\rCurrent Frame:  49, percentage:  98\r")
    assert [(u.frame, u.percent, u.total_frames, u.engine) for u in seen] == [
        (29, 58.0, 50, "melt"), (49, 98.0, 50, "melt")]


def test_reader_estimates_total_when_unknown():
    seen = []
    MeltProgressReader(seen.append).feed("Current Frame: 25, percentage: 50\n")
    assert seen[0].total_frames == 50


# ---------------------------------------------------------------------------
# _run_render_process
# ---------------------------------------------------------------------------

_SCRIPT = r"""
import sys, time
noise = "x" * 199 + "\n"
sys.stderr.write(noise * 1024)          # 200 KB before the first report
sys.stdout.write("out" * 50000)         # and 150 KB on stdout
for f, p in ((10, 20), (25, 50), (40, 80)):
    sys.stderr.write("Current Frame: %d, percentage: %d\r" % (f, p)); sys.stderr.flush()
    time.sleep(0.05)
sys.stderr.write(noise * 10)
sys.exit(3)
"""


def test_run_render_process_streams_and_drains_both_pipes():
    seen = []
    reader = MeltProgressReader(seen.append, total_frames=50)
    result = executor._run_render_process([sys.executable, "-c", _SCRIPT], 30, reader.feed)
    assert [u.frame for u in seen] == [10, 25, 40]
    assert result.returncode == 3
    assert len(result.stdout) == 150000
    assert result.stderr.count("Current Frame") == 3
    assert len(result.stderr) > 200 * 1024


def test_run_render_process_timeout_kills():
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        executor._run_render_process([sys.executable, "-c", "import time; time.sleep(30)"], 1, None)
    assert time.monotonic() - started < 10


def test_callback_error_does_not_stop_the_drain():
    def boom(_chunk):
        raise RuntimeError("consumer broke")
    result = executor._run_render_process([sys.executable, "-c", _SCRIPT], 30, boom)
    assert result.returncode == 3 and result.stderr.count("Current Frame") == 3


# ---------------------------------------------------------------------------
# verify_render_output
# ---------------------------------------------------------------------------

def _probe(streams, duration="10.0"):
    payload = json.dumps({"format": {"duration": duration}, "streams": streams})
    return subprocess.CompletedProcess([], 0, payload, "")


V = {"codec_type": "video", "duration": "10.000000", "avg_frame_rate": "25/1"}
A = {"codec_type": "audio", "duration": "10.02"}


@pytest.fixture
def out(tmp_path) -> Path:
    path = tmp_path / "out.mp4"
    path.write_bytes(b"x" * 64)
    return path


def _verify(out, streams, **kw):
    with patch.object(executor.subprocess, "run", return_value=_probe(streams, kw.pop("duration", "10.0"))):
        return executor.verify_render_output(out, **kw)


def test_no_video_stream_fails(out):
    with pytest.raises(ValueError, match="no video stream"):
        _verify(out, [A])


def test_audio_container_needs_no_video(tmp_path):
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"x" * 64)
    assert _verify(wav, [A])[0] == 10.0


def test_truncated_render_fails(out):
    short = dict(V, duration="3.200000")
    with pytest.raises(ValueError, match=r"shorter than the timeline: 3.20s of 10.00s"):
        _verify(out, [short, A], duration="3.2", expected_duration=10.0)


def test_within_tolerance_passes(out):
    assert _verify(out, [dict(V, duration="10.04"), A], duration="10.04",
                   expected_duration=10.0)[0] == pytest.approx(10.04)
    # Two frames short at 25 fps is still within the slack.
    assert _verify(out, [dict(V, duration="9.92"), A], expected_duration=10.0)


def test_missing_audio_when_expected_fails(out):
    with pytest.raises(ValueError, match="no audio stream"):
        _verify(out, [V], expect_audio=True)
    assert _verify(out, [V], expect_audio=False)


# ---------------------------------------------------------------------------
# execute_render: progress reaches the callback, 100 only after verification
# ---------------------------------------------------------------------------

def _job(tmp_path: Path, project: Path):
    from workshop_video_brain.core.models.enums import JobStatus
    from workshop_video_brain.core.models.project import RenderJob

    output = tmp_path / "out.mp4"
    return RenderJob(workspace_id="11111111-1111-1111-1111-111111111111", project_path=str(project),
                     output_path=str(output), profile="preview", log_path=f"{output}.log",
                     status=JobStatus.queued)


def _project(tmp_path: Path) -> Path:
    from tests._testkit import sequence_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

    path = tmp_path / "p.kdenlive"
    serialize_project(sequence_project(frames_each=25), path)  # 50 frames
    return path


def _fake_melt(cmd, timeout, on_chunk, *, env=None):
    assert cmd[0] == "melt" and "-progress2" in cmd
    Path(cmd[cmd.index("-consumer") + 1].removeprefix("avformat:")).write_bytes(b"x" * 64)
    for chunk in (NOISE, "Current Frame: 20, percentage: 40\n", "Current Frame: 49, percentage: 98\n"):
        on_chunk(chunk)
    return subprocess.CompletedProcess(cmd, 0, "", NOISE)


def _load(name):
    from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
    return load_profile(name)


def test_execute_render_reports_melt_progress_then_100(tmp_path, monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    monkeypatch.setattr(executor, "_run_render_process", _fake_melt)
    monkeypatch.setattr(executor, "verify_render_output", lambda p, **k: (2.0, 64))
    seen = []
    done = executor.execute_render(_job(tmp_path, _project(tmp_path)), _load("preview"),
                                   on_progress=seen.append)
    assert done.status == "succeeded", done.error_message
    assert [(u.frame, u.percent, u.total_frames, u.engine) for u in seen] == [
        (20, 40.0, 50, "melt"), (49, 98.0, 50, "melt"), (49, 100.0, 50, "melt")]


def test_no_100_when_verification_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    monkeypatch.setattr(executor, "_run_render_process", _fake_melt)

    def short(_p, **kw):
        assert kw["expected_duration"] == pytest.approx(2.0)  # 50 frames at 25 fps
        raise ValueError("Render is shorter than the timeline: 1.00s of 2.00s -- melt stopped early; see the log")

    monkeypatch.setattr(executor, "verify_render_output", short)
    seen = []
    done = executor.execute_render(_job(tmp_path, _project(tmp_path)), _load("preview"),
                                   on_progress=seen.append)
    assert done.status == "failed" and done.error_type == "invalid_output"
    assert "shorter than the timeline" in done.error_message
    assert all(u.percent < 100 for u in seen)
    assert not (tmp_path / "out.mp4").exists()


def test_progress_callback_error_does_not_fail_the_render(tmp_path, monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    monkeypatch.setattr(executor, "_run_render_process", _fake_melt)
    monkeypatch.setattr(executor, "verify_render_output", lambda p, **k: (2.0, 64))

    def broken(_update):
        raise RuntimeError("sqlite locked")

    done = executor.execute_render(_job(tmp_path, _project(tmp_path)), _load("preview"), on_progress=broken)
    assert done.status == "succeeded", done.error_message


def test_jobs_worker_persists_render_progress(tmp_path, monkeypatch):
    """The detached render job's record carries percent and engine."""
    from workshop_video_brain.core.models.enums import JobStatus
    from workshop_video_brain.edit_mcp.adapters.render.progress import RenderProgress
    from workshop_video_brain.edit_mcp.pipelines import render_pipeline
    from workshop_video_brain.workspace import jobs

    (tmp_path / "workspace.yaml").write_text("name: t\n")
    seen_records = []

    def fake_run_render(root, project, profile, *, mode, on_job, on_progress):
        for frame, pct in ((10, 20.0), (25, 50.0), (49, 100.0)):
            on_progress(RenderProgress(frame=frame, total_frames=50, percent=pct, engine="melt"))
            seen_records.append(dict(jobs.list_jobs(tmp_path, reconcile=False)[0]["progress"]))
        job = _job(tmp_path, tmp_path / "p.kdenlive")
        return job.model_copy(update={"status": JobStatus.succeeded.value})

    monkeypatch.setattr(render_pipeline, "run_render", fake_run_render)
    monkeypatch.setattr(jobs.signal, "signal", lambda *_a: None)  # keep pytest's SIGTERM handler
    record = dict(id="22222222-2222-2222-2222-222222222222", operation="render",
                  parameters={"project_file": str(tmp_path / "p.kdenlive")}, status="queued",
                  created_at=time.time(), updated_at=time.time(), pid=None, outputs=[], error="",
                  progress={})
    with jobs._db(tmp_path) as connection:
        jobs._save(connection, record)
    jobs._run_worker(tmp_path, record["id"])
    assert seen_records[-1]["stage"] == "rendering"
    assert seen_records[-1]["percent"] == 100.0
    assert seen_records[-1]["engine"] == "melt"
    assert seen_records[0]["completed"] == 11 and seen_records[0]["total"] == 50
