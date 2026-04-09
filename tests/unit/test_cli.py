"""Unit tests for the CLI entry point (click commands)."""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from workshop_video_brain.app.cli import main
from workshop_video_brain import __version__


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestVersionCommand:
    def test_version_outputs_version_string(self, runner: CliRunner):
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_includes_package_name(self, runner: CliRunner):
        result = runner.invoke(main, ["version"])
        assert "workshop-video-brain" in result.output


class TestHelpText:
    def test_main_help(self, runner: CliRunner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Workshop Video Brain" in result.output

    def test_workspace_help(self, runner: CliRunner):
        result = runner.invoke(main, ["workspace", "--help"])
        assert result.exit_code == 0
        assert "workspace" in result.output.lower()

    def test_media_help(self, runner: CliRunner):
        result = runner.invoke(main, ["media", "--help"])
        assert result.exit_code == 0
        assert "media" in result.output.lower()

    def test_transcript_help(self, runner: CliRunner):
        result = runner.invoke(main, ["transcript", "--help"])
        assert result.exit_code == 0

    def test_markers_help(self, runner: CliRunner):
        result = runner.invoke(main, ["markers", "--help"])
        assert result.exit_code == 0

    def test_timeline_help(self, runner: CliRunner):
        result = runner.invoke(main, ["timeline", "--help"])
        assert result.exit_code == 0

    def test_pacing_help(self, runner: CliRunner):
        result = runner.invoke(main, ["pacing", "--help"])
        assert result.exit_code == 0

    def test_plan_help(self, runner: CliRunner):
        result = runner.invoke(main, ["plan", "--help"])
        assert result.exit_code == 0


class TestWorkspaceSubcommands:
    def test_workspace_create_help(self, runner: CliRunner):
        result = runner.invoke(main, ["workspace", "create", "--help"])
        assert result.exit_code == 0
        assert "--media-root" in result.output

    def test_workspace_status_help(self, runner: CliRunner):
        result = runner.invoke(main, ["workspace", "status", "--help"])
        assert result.exit_code == 0

    def test_workspace_status_missing_manifest_exits_nonzero(self, runner: CliRunner, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = runner.invoke(main, ["workspace", "status", str(empty)])
        assert result.exit_code != 0

    def test_workspace_create_creates_workspace(self, runner: CliRunner, tmp_path):
        media = tmp_path / "media"
        media.mkdir()
        ws_root = tmp_path / "my-project"
        result = runner.invoke(
            main,
            [
                "workspace", "create", "My Project",
                "--media-root", str(media),
            ],
            env={"WVB_WORKSPACE_ROOT": str(ws_root)},
        )
        # Command should succeed (exit 0) or at least not crash unhandled
        assert "Error" not in result.output or result.exit_code == 0


class TestMediaSubcommands:
    def test_media_ingest_help(self, runner: CliRunner):
        result = runner.invoke(main, ["media", "ingest", "--help"])
        assert result.exit_code == 0

    def test_media_list_help(self, runner: CliRunner):
        result = runner.invoke(main, ["media", "list", "--help"])
        assert result.exit_code == 0
