"""Unit tests for the research_run / research_export_package MCP tools."""
from __future__ import annotations

import json
from pathlib import Path

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.server.tools import research_candidates, research_package

FIXTURE = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()

pytestmark = requires_ffmpeg_ffprobe


def _run(tmp_path, **kwargs):
    output_dir = tmp_path / "run"
    return call_tool(
        research_package.research_run,
        str(FIXTURE),
        str(output_dir),
        start_seconds=0.0,
        end_seconds=2.0,
        **kwargs,
    ), output_dir


def _generate(tmp_path, **kwargs):
    output_dir = tmp_path / "candidates"
    return call_tool(
        research_candidates.research_generate_candidates,
        str(FIXTURE),
        str(output_dir),
        start_seconds=0.0,
        end_seconds=2.0,
        **kwargs,
    ), output_dir


def test_research_run_writes_package(tmp_path):
    result, output_dir = _run(tmp_path)

    assert result["status"] != "error"
    data = result["data"] if "data" in result else result
    assert "regions" in data
    assert "captures" in data
    assert "errors" in data
    assert len(data["captures"]) >= 1
    assert (output_dir / "index.md").exists()
    assert (output_dir / "manifest.json").exists()
    screenshots = list((output_dir / "screenshots").glob("001-*"))
    assert len(screenshots) >= 1


def test_research_run_missing_video_returns_missing_file(tmp_path):
    result = call_tool(
        research_package.research_run,
        str(tmp_path / "nope.mp4"),
        str(tmp_path / "out"),
    )

    assert result["status"] == "error"
    assert result["error_type"] == "missing_file"


def test_research_run_nonempty_dir_without_overwrite_is_invalid_input(tmp_path):
    _run(tmp_path)

    result, _ = _run(tmp_path)

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"


def test_research_run_overwrite_replaces_package(tmp_path):
    _run(tmp_path)

    result, output_dir = _run(tmp_path, overwrite=True)

    assert result["status"] != "error"
    assert (output_dir / "manifest.json").exists()


def test_research_export_package_no_selections_uses_top_scored(tmp_path):
    generated, candidates_dir = _generate(tmp_path)
    gen_data = generated["data"] if "data" in generated else generated
    assert gen_data["selections"] == []

    export_dir = tmp_path / "export"
    result = call_tool(
        research_package.research_export_package,
        str(candidates_dir),
        str(export_dir),
    )

    assert result["status"] != "error"
    data = result["data"] if "data" in result else result
    manifest_path = Path(data["output_dir"]) / "manifest.json"
    assert manifest_path.exists()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(payload["captures"]) >= 1


def test_research_export_package_uses_recorded_selection(tmp_path):
    generated, candidates_dir = _generate(tmp_path)
    gen_data = generated["data"] if "data" in generated else generated
    chosen = gen_data["candidates"][0]

    select_export_dir = tmp_path / "select-export"
    call_tool(
        research_candidates.research_select_candidate,
        str(candidates_dir),
        [chosen["id"]],
        output_dir=str(select_export_dir),
    )

    export_dir = tmp_path / "package-export"
    result = call_tool(
        research_package.research_export_package,
        str(candidates_dir),
        str(export_dir),
    )

    assert result["status"] != "error"
    data = result["data"] if "data" in result else result
    manifest_path = Path(data["output_dir"]) / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["captures"][0]["timestamp_seconds"] == chosen["timestamp_seconds"]


def test_research_export_package_missing_manifest_returns_not_found(tmp_path):
    result = call_tool(
        research_package.research_export_package,
        str(tmp_path / "does-not-exist"),
        str(tmp_path / "out"),
    )

    assert result["status"] == "error"
    assert result["error_type"] == "not_found"


def test_research_export_package_nonempty_dir_without_overwrite_is_invalid_input(tmp_path):
    _generated, candidates_dir = _generate(tmp_path)

    export_dir = tmp_path / "export"
    call_tool(
        research_package.research_export_package,
        str(candidates_dir),
        str(export_dir),
    )

    result = call_tool(
        research_package.research_export_package,
        str(candidates_dir),
        str(export_dir),
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"


def test_overwrite_never_honored_under_protected_paths(tmp_path):
    protected = tmp_path / "media" / "raw" / "research_out"
    protected.mkdir(parents=True)
    (protected / "manifest.json").write_text("{}", encoding="utf-8")

    result = call_tool(
        research_package.research_run,
        str(FIXTURE),
        str(protected),
        start_seconds=0.0,
        end_seconds=1.0,
        overwrite=True,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert (protected / "manifest.json").exists()
