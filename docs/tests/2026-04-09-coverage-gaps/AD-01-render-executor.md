---
scenario_id: "AD-01"
title: "Render Executor"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario AD-01: Render Executor

## Description
Tests `execute_render` and `check_codec_available` in
`edit_mcp/adapters/render/executor.py`.  The executor wraps subprocess calls to
`melt` / `ffmpeg`, captures logs, and returns an updated `RenderJob`.  All
subprocess interaction is mocked so no real render tool is required.

Key paths under test:
- `check_codec_available` — runs `ffmpeg -codecs`, searches output, handles
  `FileNotFoundError` / `TimeoutExpired`.
- `execute_render` — success path (returncode 0 → `succeeded`), failure path
  (non-zero returncode → `failed`), `TimeoutExpired` → `failed`,
  `FileNotFoundError` → `failed`, log file written on each path.
- `_build_command` routing — `.kdenlive` project → `melt` command;
  other extension → `ffmpeg` command.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- `workshop_video_brain` importable via `uv run`.
- No real `ffmpeg` or `melt` binary required (all subprocess calls mocked).
- `tmp_path` pytest fixture used for log file paths.

## Test Cases

```python
# tests/unit/test_render_executor.py
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.executor import (
    check_codec_available,
    execute_render,
    DEFAULT_TIMEOUT_SECONDS,
)
from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_profile() -> RenderProfile:
    return RenderProfile(
        name="test",
        width=1920,
        height=1080,
        fps=25.0,
        video_codec="libx264",
        video_bitrate="8M",
        audio_codec="aac",
        audio_bitrate="192k",
    )


@pytest.fixture()
def render_job(tmp_path: Path) -> RenderJob:
    return RenderJob(
        workspace_id=uuid4(),
        project_path=str(tmp_path / "project.kdenlive"),
        profile="test",
        output_path=str(tmp_path / "renders" / "out.mp4"),
        log_path=str(tmp_path / "renders" / "out.mp4.log"),
    )


# ---------------------------------------------------------------------------
# check_codec_available
# ---------------------------------------------------------------------------

class TestCheckCodecAvailable:
    def test_returns_true_when_codec_in_output(self):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.LS libx264              H.264 / AVC / MPEG-4 AVC\n"
            " DEV.L. aac                  AAC (Advanced Audio Coding)\n"
        )
        with patch("subprocess.run", return_value=mock_result):
            assert check_codec_available("libx264") is True

    def test_returns_false_when_codec_absent(self):
        mock_result = MagicMock()
        mock_result.stdout = " DEV.LS libx265   H.265\n"
        with patch("subprocess.run", return_value=mock_result):
            assert check_codec_available("libx264") is False

    def test_returns_false_on_file_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert check_codec_available("libx264") is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)):
            assert check_codec_available("libx264") is False

    def test_returns_false_on_empty_output(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            assert check_codec_available("libx264") is False


# ---------------------------------------------------------------------------
# execute_render — success path
# ---------------------------------------------------------------------------

class TestExecuteRenderSuccess:
    def test_returns_succeeded_status_on_returncode_0(
        self, render_job: RenderJob, base_profile: RenderProfile, tmp_path: Path
    ):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "render complete"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = execute_render(
                render_job, base_profile,
                _command_override=["echo", "ok"],
            )

        assert result.status == JobStatus.succeeded

    def test_started_at_is_set(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = execute_render(render_job, base_profile, _command_override=["echo"])
        assert result.started_at is not None

    def test_log_file_written_on_success(
        self, render_job: RenderJob, base_profile: RenderProfile, tmp_path: Path
    ):
        mock_result = MagicMock(returncode=0, stdout="done", stderr="")
        log_path = Path(render_job.log_path)

        with patch("subprocess.run", return_value=mock_result):
            execute_render(render_job, base_profile, _command_override=["echo"])

        assert log_path.exists()
        content = log_path.read_text()
        assert "Return code: 0" in content


# ---------------------------------------------------------------------------
# execute_render — failure paths
# ---------------------------------------------------------------------------

class TestExecuteRenderFailure:
    def test_non_zero_returncode_returns_failed(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        mock_result = MagicMock(returncode=1, stdout="", stderr="error msg")
        with patch("subprocess.run", return_value=mock_result):
            result = execute_render(render_job, base_profile, _command_override=["false"])
        assert result.status == JobStatus.failed

    def test_completed_at_set_on_failure(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        mock_result = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = execute_render(render_job, base_profile, _command_override=["false"])
        assert result.completed_at is not None

    def test_timeout_returns_failed(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="melt", timeout=10),
        ):
            result = execute_render(render_job, base_profile, _command_override=["sleep"])
        assert result.status == JobStatus.failed

    def test_file_not_found_returns_failed(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        with patch("subprocess.run", side_effect=FileNotFoundError("melt not found")):
            result = execute_render(render_job, base_profile)
        assert result.status == JobStatus.failed

    def test_unexpected_exception_returns_failed(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        with patch("subprocess.run", side_effect=RuntimeError("oops")):
            result = execute_render(render_job, base_profile, _command_override=["bad"])
        assert result.status == JobStatus.failed

    def test_log_written_on_timeout(
        self, render_job: RenderJob, base_profile: RenderProfile
    ):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="melt", timeout=5),
        ):
            execute_render(render_job, base_profile, timeout_seconds=5, _command_override=["sleep"])
        log_path = Path(render_job.log_path)
        assert log_path.exists()
        assert "TIMEOUT" in log_path.read_text()


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

class TestBuildCommand:
    def test_kdenlive_project_uses_melt(
        self, base_profile: RenderProfile, tmp_path: Path
    ):
        job = RenderJob(
            workspace_id=uuid4(),
            project_path=str(tmp_path / "edit.kdenlive"),
            output_path=str(tmp_path / "out.mp4"),
        )
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return mock_result

        with patch("subprocess.run", side_effect=fake_run):
            execute_render(job, base_profile)

        assert captured["cmd"][0] == "melt"

    def test_non_kdenlive_project_uses_ffmpeg(
        self, base_profile: RenderProfile, tmp_path: Path
    ):
        job = RenderJob(
            workspace_id=uuid4(),
            project_path=str(tmp_path / "source.mp4"),
            output_path=str(tmp_path / "out.mp4"),
        )
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return mock_result

        with patch("subprocess.run", side_effect=fake_run):
            execute_render(job, base_profile)

        assert captured["cmd"][0] == "ffmpeg"

    def test_ffmpeg_command_includes_codec_and_bitrate(
        self, base_profile: RenderProfile, tmp_path: Path
    ):
        job = RenderJob(
            workspace_id=uuid4(),
            project_path=str(tmp_path / "source.mp4"),
            output_path=str(tmp_path / "out.mp4"),
        )
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return mock_result

        with patch("subprocess.run", side_effect=fake_run):
            execute_render(job, base_profile)

        cmd_str = " ".join(captured["cmd"])
        assert "libx264" in cmd_str
        assert "8M" in cmd_str
        assert "aac" in cmd_str
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/executor.py`
2. Create `tests/unit/test_render_executor.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_render_executor.py -v`

## Expected Results
- `check_codec_available` returns `True` only when codec name appears in mocked stdout.
- `execute_render` returns `JobStatus.succeeded` when `returncode == 0`.
- `execute_render` returns `JobStatus.failed` for non-zero exit, timeout, and missing binary.
- Log file is created and contains expected content on all paths.
- `.kdenlive` project routes to `melt`; other extensions route to `ffmpeg`.
- `started_at` is populated when job transitions to running.
- `completed_at` is populated when job reaches a terminal state.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
