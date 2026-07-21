"""Unit tests for the research_generate_candidates / research_select_candidate MCP tools."""
from __future__ import annotations

from pathlib import Path

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.server.tools import research_candidates

FIXTURE = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()

pytestmark = requires_ffmpeg_ffprobe


def _generate(tmp_path, **kwargs):
    output_dir = tmp_path / "run"
    return call_tool(
        research_candidates.research_generate_candidates,
        str(FIXTURE),
        str(output_dir),
        start_seconds=0.0,
        end_seconds=2.0,
        **kwargs,
    ), output_dir


def test_research_generate_candidates_writes_manifest(tmp_path):
    result, output_dir = _generate(tmp_path)

    assert result["status"] == "success" or result.get("status") != "error"
    data = result["data"] if "data" in result else result
    assert data["schema_version"] == 1
    assert len(data["candidates"]) >= 1
    assert (output_dir / "candidates.json").exists()


def test_research_generate_candidates_missing_video_returns_missing_file(tmp_path):
    result = call_tool(
        research_candidates.research_generate_candidates,
        str(tmp_path / "nope.mp4"),
        str(tmp_path / "out"),
    )

    assert result["status"] == "error"
    assert result["error_type"] == "missing_file"


def test_research_generate_candidates_nonempty_dir_without_overwrite_is_invalid_input(
    tmp_path,
):
    _generate(tmp_path)

    result = call_tool(
        research_candidates.research_generate_candidates,
        str(FIXTURE),
        str(tmp_path / "run"),
        start_seconds=0.0,
        end_seconds=2.0,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"


def test_research_generate_candidates_overwrite_regenerates(tmp_path):
    _generate(tmp_path)

    result, output_dir = _generate(tmp_path, overwrite=True)
    data = result["data"] if "data" in result else result

    assert len(data["candidates"]) >= 1
    assert (output_dir / "candidates.json").exists()


def test_research_select_candidate_exports_package_naming_timestamp(tmp_path):
    generated, output_dir = _generate(tmp_path)
    gen_data = generated["data"] if "data" in generated else generated
    chosen = gen_data["candidates"][0]

    result = call_tool(
        research_candidates.research_select_candidate,
        str(output_dir),
        [chosen["id"]],
    )

    assert result["status"] != "error"
    data = result["data"] if "data" in result else result
    export_dir = Path(data["output_dir"])
    manifest_path = export_dir / "manifest.json"
    assert manifest_path.exists()

    import json

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["captures"][0]["timestamp_seconds"] == chosen["timestamp_seconds"]


def test_research_select_candidate_unknown_id_lists_valid_ids(tmp_path):
    _generated, output_dir = _generate(tmp_path)

    result = call_tool(
        research_candidates.research_select_candidate,
        str(output_dir),
        ["cand-999"],
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input"
    assert "cand-999" in result["unknown_ids"]


def test_research_select_candidate_missing_manifest_returns_not_found(tmp_path):
    result = call_tool(
        research_candidates.research_select_candidate,
        str(tmp_path / "does-not-exist"),
        ["cand-001"],
    )

    assert result["status"] == "error"
    assert result["error_type"] == "not_found"
    assert "candidates.json" in result["given"]
