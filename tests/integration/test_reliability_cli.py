"""The reliability CLI entry points, driven for real (prompt 08).

Every job here runs in a real detached worker: nothing about the process
group, the render registry or the on-disk cleanup is monkeypatched.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from tests._testkit import call_tool, requires_ffmpeg_ffprobe, requires_melt
from workshop_video_brain.app.cli import main
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.server.tools import clips_nle, timeline_project
from workshop_video_brain.workspace import jobs
from workshop_video_brain.workspace.manager import WorkspaceManager

pytestmark = [
    requires_ffmpeg_ffprobe,
    pytest.mark.skipif(os.name != "posix", reason="detached jobs are POSIX only"),
]

FIXTURE = Path(__file__).parents[1] / "fixtures/media_generated/test_clip_1080p2997_5s.mp4"
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
SCRIPT_TEXT = "First sand the wooden board smooth with sandpaper. Sand the wooden board smooth with sandpaper."


def _invoke(*args: str):
    return CliRunner().invoke(main, list(args))


def _json(*args: str) -> dict:
    result = _invoke(*args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _wait(workspace: Path, job_id: str, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _json("jobs", "status", str(workspace), job_id)
        if job["status"] in TERMINAL:
            return job
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} still {job['status']} after {timeout}s")


@pytest.fixture
def stop_active_jobs():
    """Cancel anything still active, so a failing test never leaks a worker."""
    workspaces: list[Path] = []
    yield workspaces.append
    for workspace in workspaces:
        for job in jobs.list_jobs(workspace):
            if job["status"] not in TERMINAL:
                jobs.cancel_job(workspace, job["id"])
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and jobs.get_job(workspace, job["id"])["status"] not in TERMINAL:
                    time.sleep(0.1)


@pytest.fixture
def empty_workspace(tmp_path, monkeypatch, stop_active_jobs) -> Path:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    root = tmp_path / "workspace"
    WorkspaceManager.create("Sanding tutorial", tmp_path, workspace_root=root)
    stop_active_jobs(root)
    return root


@pytest.fixture
def workspace(empty_workspace: Path) -> Path:
    root = empty_workspace
    shutil.copyfile(FIXTURE, root / "media/raw/sanding.mp4")
    transcript = Transcript(
        asset_id=uuid4(), engine="manual", raw_text=SCRIPT_TEXT,
        segments=[TranscriptSegment(start_seconds=0, end_seconds=4, text=SCRIPT_TEXT)],
    )
    (root / "transcripts/sanding_transcript.json").write_text(transcript.to_json())
    (root / "reports/script.json").write_text(
        json.dumps({"steps": [{"description": SCRIPT_TEXT, "chapter_title": "Sand wooden board"}]})
    )
    return root


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ("not json", "Expected a JSON object"),
        ('["a", "list"]', "Expected a JSON object"),
        ('{"nonsense": 1}', "nonsense"),
    ],
    ids=["non_json", "non_object", "unknown_key"],
)
def test_jobs_submit_refuses_bad_parameters(empty_workspace, parameters, expected):
    result = _invoke("jobs", "submit", str(empty_workspace), "proxy", "--parameters", parameters)
    assert result.exit_code != 0
    assert expected in result.output
    assert jobs.list_jobs(empty_workspace) == []


def test_project_status_creates_no_files(workspace):
    before = {path: path.stat().st_mtime_ns for path in workspace.rglob("*")}
    status = _json("project-status", str(workspace))
    assert status["readiness"]["review"] is False
    assert {path: path.stat().st_mtime_ns for path in workspace.rglob("*")} == before


def test_workflow_on_empty_workspace_fails_clearly_and_retries_with_new_id(empty_workspace):
    job = _json("workflow", str(empty_workspace), "--through", "footage")
    finished = _wait(empty_workspace, job["id"])
    assert finished["status"] == "failed"
    assert "Copy recordings" in finished["error"]
    # The job record turns terminal just before the worker process exits, and retry
    # refuses while its group is alive.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and _group_members(job["pid"]):
        time.sleep(0.05)
    retried = _json("jobs", "retry", str(empty_workspace), job["id"])
    assert retried["id"] != job["id"]
    assert _wait(empty_workspace, retried["id"])["status"] == "failed"


@requires_melt
def test_workflow_through_review_then_resumes_without_rerunning(workspace):
    job = _json("workflow", str(workspace), "--through", "review")
    finished = _wait(workspace, job["id"], timeout=120)
    assert finished["status"] == "succeeded", finished["error"]
    status = _json("project-status", str(workspace))
    assert all(status["readiness"].values()), status
    project = Path(finished["result"]["project_file"])
    preview = Path(status["latest_preview"])
    review = workspace / "reports/workflow_review.md"
    assert project.is_file() and preview.stat().st_size > 0 and review.is_file()

    times = {path: path.stat().st_mtime_ns for path in (project, preview, review)}
    again = _json("workflow", str(workspace), "--through", "review")
    assert _wait(workspace, again["id"], timeout=120)["status"] == "succeeded"
    assert {path: path.stat().st_mtime_ns for path in times} == times


def _project_with_inserts(workspace: Path, count: int) -> Path:
    created = call_tool(timeline_project.project_create_working_copy, str(workspace))
    assert created["status"] == "success", created
    source = workspace / "media/raw/sanding.mp4"
    for _ in range(count):
        inserted = call_tool(clips_nle.clip_insert, str(workspace), str(source))
        assert inserted["status"] == "success", inserted
    return Path(inserted["data"]["kdenlive_path"])


def _group_members(pgid: int) -> list[str]:
    listing = subprocess.run(
        ["ps", "-eo", "pgid=,stat=,comm="], capture_output=True, text=True, check=True, timeout=10,
    )
    members = []
    for line in listing.stdout.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0] == str(pgid) and not fields[1].startswith("Z"):
            members.append(fields[2])
    return members


@requires_melt
def test_render_job_registers_its_output(workspace):
    project = _project_with_inserts(workspace, 1)
    job = _json("jobs", "submit", str(workspace), "render", "--parameters",
                json.dumps({"profile": "preview", "project_file": str(project)}))
    finished = _wait(workspace, job["id"], timeout=120)
    assert finished["status"] == "succeeded", finished["error"]
    output = Path(finished["result"]["output_path"])
    assert output.stat().st_size > 0

    listing = _invoke("render", "status", str(workspace))
    assert listing.exit_code == 0 and str(output) in listing.output

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames,avg_frame_rate",
         "-of", "json", str(output)],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout)
    video = [stream for stream in probe["streams"] if stream["codec_type"] == "video"]
    assert len(video) == 1
    assert int(video[0]["nb_frames"]) > 100  # a 5 s source, not a stub


@requires_melt
def test_cancelling_a_running_render_kills_the_group_and_leaves_no_output(workspace):
    project = _project_with_inserts(workspace, 8)
    before = {path for path in (workspace / "renders").rglob("*") if path.suffix == ".mp4"}
    job = _json("jobs", "submit", str(workspace), "render", "--parameters",
                json.dumps({"profile": "preview", "project_file": str(project)}))
    pgid = job["pid"]

    # Cancel only once melt itself is up: cancelling a queued worker proves nothing.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not any("melt" in name for name in _group_members(pgid)):
        time.sleep(0.05)
    try:
        assert any("melt" in name for name in _group_members(pgid)), "melt never started"
        assert jobs.get_job(workspace, job["id"])["status"] == "running"

        _json("jobs", "cancel", str(workspace), job["id"])
        finished = _wait(workspace, job["id"], timeout=15)
        assert finished["status"] == "cancelled", finished

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and _group_members(pgid):
            time.sleep(0.1)
        assert _group_members(pgid) == []
    finally:
        if _group_members(pgid):
            os.killpg(pgid, signal.SIGKILL)

    after = {path for path in (workspace / "renders").rglob("*") if path.suffix == ".mp4"}
    assert after == before, f"partial render left behind: {after - before}"

    retried = _json("jobs", "retry", str(workspace), job["id"])
    assert retried["id"] != job["id"]
    jobs.cancel_job(workspace, retried["id"])
