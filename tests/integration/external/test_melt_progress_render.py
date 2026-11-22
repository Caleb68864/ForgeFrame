"""Real melt: render progress reaches the callback, and a short render fails (prompt 18)."""
from __future__ import annotations

from pathlib import Path

from tests._testkit import sequence_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.adapters.render import executor
from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest


def _workspace(tmp_path: Path, frames_each: int) -> tuple[Path, Path]:
    root = tmp_path / "ws"
    WorkspaceManager.create("Progress", tmp_path, workspace_root=root)
    project = serialize_versioned(sequence_project(frames_each=frames_each), root, read_manifest(root).slug)
    return root, project


def test_render_reports_progress_and_ends_at_100(melt_bin, tmp_path, monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    root, project = _workspace(tmp_path, frames_each=125)  # 250 frames, 10 s
    seen = []

    job = run_render(root, project, "preview", on_progress=seen.append)

    assert job.status == "succeeded", job.error_message
    assert len(seen) >= 2, seen
    frames = [u.frame for u in seen]
    assert frames == sorted(frames)
    assert all(u.engine == "melt" and u.total_frames == 250 for u in seen)
    assert seen[-1].percent == 100.0
    assert all(u.percent < 100 for u in seen[:-1])


def test_render_cut_short_fails_as_invalid_output(melt_bin, tmp_path, monkeypatch):
    monkeypatch.delenv("WVB_RENDER_ENGINE", raising=False)
    root, project = _workspace(tmp_path, frames_each=50)  # 100 frames, 4 s
    real_build = executor._build_command

    def stops_early(job, profile):
        cmd = real_build(job, profile)
        at = cmd.index(str(job.project_path)) + 1
        return [*cmd[:at], "out=24", *cmd[at:]]  # melt renders 1 s and exits 0

    monkeypatch.setattr(executor, "_build_command", stops_early)
    job = run_render(root, project, "preview")

    assert job.status == "failed"
    assert job.error_type == "invalid_output"
    assert "shorter than the timeline" in job.error_message
    assert not Path(job.output_path).exists()
