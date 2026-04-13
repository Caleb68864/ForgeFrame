"""Unit tests for `workshop-video-brain catalog ...` subcommand (sub-spec 3)."""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from workshop_video_brain.app.cli import main


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "effect_xml" / "build_three"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCatalogHelp:
    # SS3-04
    def test_catalog_help_lists_regenerate(self, runner: CliRunner):
        result = runner.invoke(main, ["catalog", "--help"])
        assert result.exit_code == 0
        assert "regenerate" in result.output

    def test_catalog_regenerate_help_lists_flags(self, runner: CliRunner):
        result = runner.invoke(main, ["catalog", "regenerate", "--help"])
        assert result.exit_code == 0
        assert "--no-upstream-check" in result.output
        assert "--output" in result.output
        assert "--source-dir" in result.output


class TestCatalogRegenerate:
    # SS3-12
    def test_regenerate_against_fixtures(self, runner: CliRunner, tmp_path: Path):
        out = tmp_path / "out.py"
        result = runner.invoke(
            main,
            [
                "catalog",
                "regenerate",
                "--no-upstream-check",
                "--output",
                str(out),
                "--source-dir",
                str(FIXTURE_DIR),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert out.stat().st_size > 0
        text = out.read_text()
        assert "CATALOG" in text
        assert "acompressor" in text

    def test_regenerate_missing_source_dir(
        self, runner: CliRunner, tmp_path: Path
    ):
        out = tmp_path / "out.py"
        result = runner.invoke(
            main,
            [
                "catalog",
                "regenerate",
                "--no-upstream-check",
                "--output",
                str(out),
                "--source-dir",
                "/nonexistent/path_for_test",
            ],
        )
        assert result.exit_code != 0
        combined = result.output + (
            result.stderr if hasattr(result, "stderr") and result.stderr_bytes else ""
        )
        # Error message should mention Kdenlive or the path
        assert "Kdenlive" in result.output or "/nonexistent/path_for_test" in result.output
