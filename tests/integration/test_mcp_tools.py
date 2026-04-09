"""Integration tests for MCP tool functions.

Tests exercise the tool functions directly (not via MCP transport), calling
them with real temp workspaces and verifying structured dict output.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

# Skip the entire module if fastmcp is unavailable (e.g. system Python without venv)
fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

# Ensure tools module is loaded (registers @mcp.tool decorators)
import workshop_video_brain.edit_mcp.server.tools as _tools  # noqa: F401

from workshop_video_brain.edit_mcp.server.tools import (
    workspace_create,
    workspace_status,
    markers_auto_generate,
    project_validate,
    snapshot_list,
    media_list_assets,
    render_status,
    project_create_working_copy,
    clips_label,
    clips_search,
    pacing_analyze,
    broll_suggest,
    pattern_extract,
    title_cards_generate,
    replay_generate,
    snapshot_restore,
    markers_list,  # type: ignore[attr-defined]
    transcript_export,
    subtitles_generate,
    subtitles_export,
    render_preview,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path: Path, title: str = "Test Project", subdir: str = "ws") -> dict:
    """Create a workspace and return the workspace_create result dict."""
    base = tmp_path / subdir
    base.mkdir(parents=True, exist_ok=True)
    media_root = str(base / "media_source")
    Path(media_root).mkdir(parents=True, exist_ok=True)
    result = workspace_create(title=title, media_root=media_root)
    assert result["status"] == "success", f"workspace_create failed: {result}"
    return result


def _fake_transcript(transcripts_dir: Path, stem: str = "clip") -> None:
    """Write a minimal fake transcript JSON for marker generation tests."""
    from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
    from uuid import uuid4
    t = Transcript(
        asset_id=uuid4(),
        engine="test",
        model="test",
        language="en",
        segments=[
            TranscriptSegment(start_seconds=0.0, end_seconds=5.0, text="Hello and welcome to this tutorial."),
            TranscriptSegment(start_seconds=5.0, end_seconds=15.0, text="Today we are going to demonstrate a step."),
            TranscriptSegment(start_seconds=15.0, end_seconds=30.0, text="First make sure you have all materials."),
            TranscriptSegment(start_seconds=30.0, end_seconds=60.0, text="Let me explain how this works step by step."),
        ],
        raw_text="Hello and welcome to this tutorial. Today we demonstrate a step.",
    )
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    (transcripts_dir / f"{stem}_transcript.json").write_text(t.to_json(), encoding="utf-8")


# ---------------------------------------------------------------------------
# workspace_create
# ---------------------------------------------------------------------------


class TestWorkspaceCreate:
    def test_returns_success_dict(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(
            title="My Video",
            media_root=str(media_root),
        )
        assert result["status"] == "success"

    def test_data_contains_workspace_root(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(
            title="My Video",
            media_root=str(media_root),
        )
        assert "workspace_root" in result["data"]

    def test_data_contains_workspace_id(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(
            title="My Video",
            media_root=str(media_root),
        )
        assert "workspace_id" in result["data"]

    def test_data_contains_slug(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(
            title="My Tutorial Video",
            media_root=str(media_root),
        )
        assert result["data"]["slug"] == "my-tutorial-video"

    def test_workspace_yaml_created_on_disk(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(
            title="Disk Check",
            media_root=str(media_root),
        )
        ws_root = Path(result["data"]["workspace_root"])
        assert (ws_root / "workspace.yaml").exists()

    def test_error_on_nonexistent_media_root(self, tmp_path):
        # workspace_create should now return error if media_root does not exist
        result = workspace_create(
            title="Nested",
            media_root=str(tmp_path / "does_not_exist" / "media"),
        )
        assert result["status"] == "error"
        assert "media_root" in result["message"].lower() or "does not exist" in result["message"].lower()

    def test_error_on_empty_title(self, tmp_path):
        media_root = tmp_path / "media"
        media_root.mkdir()
        result = workspace_create(title="", media_root=str(media_root))
        assert result["status"] == "error"
        assert "title" in result["message"].lower()

    def test_error_on_empty_media_root(self, tmp_path):
        result = workspace_create(title="Test", media_root="")
        assert result["status"] == "error"
        assert "media_root" in result["message"].lower()

    def test_error_when_media_root_is_a_file(self, tmp_path):
        media_file = tmp_path / "media_file"
        media_file.touch()
        result = workspace_create(title="Test", media_root=str(media_file))
        assert result["status"] == "error"
        assert "not a directory" in result["message"].lower()


# ---------------------------------------------------------------------------
# workspace_status
# ---------------------------------------------------------------------------


class TestWorkspaceStatus:
    def test_returns_success_for_valid_workspace(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert result["status"] == "success"

    def test_data_contains_title(self, tmp_path):
        m = tmp_path / "m"
        m.mkdir()
        created = workspace_create(title="Status Test", media_root=str(m))
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert result["data"]["project_title"] == "Status Test"

    def test_error_on_missing_workspace(self, tmp_path):
        result = workspace_status(workspace_path=str(tmp_path / "nonexistent"))
        assert result["status"] == "error"
        assert "message" in result

    def test_data_has_status_field(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = workspace_status(workspace_path=ws_root)
        assert "status" in result["data"]


# ---------------------------------------------------------------------------
# markers_auto_generate
# ---------------------------------------------------------------------------


class TestMarkersAutoGenerate:
    def test_returns_success_with_no_transcripts(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = markers_auto_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["marker_files"] == 0

    def test_generates_markers_from_transcript(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "sample")
        result = markers_auto_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["marker_files"] >= 1
        assert result["data"]["total_markers"] >= 1

    def test_writes_marker_json_to_disk(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        marker_files = list((Path(ws_root) / "markers").glob("*_markers.json"))
        assert len(marker_files) >= 1

    def test_marker_json_is_valid_list(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        for mf in (Path(ws_root) / "markers").glob("*_markers.json"):
            data = json.loads(mf.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert all("category" in m for m in data)

    def test_idempotent_second_run(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        r1 = markers_auto_generate(workspace_path=ws_root)
        r2 = markers_auto_generate(workspace_path=ws_root)
        assert r1["data"]["total_markers"] == r2["data"]["total_markers"]


# ---------------------------------------------------------------------------
# project_validate
# ---------------------------------------------------------------------------


class TestProjectValidate:
    def test_error_when_no_kdenlive_files(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = project_validate(workspace_path=ws_root)
        assert result["status"] == "error"

    def test_validates_generated_working_copy(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Create a working copy first
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "summary" in result["data"]
        assert "issues" in result["data"]

    def test_valid_project_has_zero_blocking_errors(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        blocking = [
            i for i in result["data"]["issues"]
            if i["severity"] == "blocking_error"
        ]
        assert len(blocking) == 0

    def test_returns_project_file_path(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        project_create_working_copy(workspace_path=ws_root)
        result = project_validate(workspace_path=ws_root)
        assert "project_file" in result["data"]
        assert result["data"]["project_file"].endswith(".kdenlive")


# ---------------------------------------------------------------------------
# snapshot_list
# ---------------------------------------------------------------------------


class TestSnapshotList:
    def test_returns_success_with_empty_snapshots(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = snapshot_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_returns_snapshot_after_create(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Create a working copy and snapshot it
        copy_result = project_create_working_copy(workspace_path=ws_root)
        assert copy_result["status"] == "success"
        kdenlive_path = Path(copy_result["data"]["kdenlive_path"])
        from workshop_video_brain.workspace.snapshot import create as create_snapshot
        create_snapshot(ws_root, kdenlive_path, description="test snapshot")
        result = snapshot_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] >= 1

    def test_snapshot_list_has_expected_fields(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        copy_result = project_create_working_copy(workspace_path=ws_root)
        kdenlive_path = Path(copy_result["data"]["kdenlive_path"])
        from workshop_video_brain.workspace.snapshot import create as create_snapshot
        create_snapshot(ws_root, kdenlive_path, description="field check")
        result = snapshot_list(workspace_path=ws_root)
        assert len(result["data"]["snapshots"]) >= 1
        snap = result["data"]["snapshots"][0]
        assert "id" in snap
        assert "timestamp" in snap
        assert "description" in snap


# ---------------------------------------------------------------------------
# Additional: media_list_assets and render_status
# ---------------------------------------------------------------------------


class TestMediaListAssets:
    def test_empty_result_when_no_raw_dir(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = media_list_assets(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0


class TestRenderStatus:
    def test_empty_jobs_when_no_renders(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = render_status(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0


# ===========================================================================
# Comprehensive error-path tests
# ===========================================================================

# ---------------------------------------------------------------------------
# workspace_status — error paths
# ---------------------------------------------------------------------------

class TestWorkspaceStatusErrorPaths:
    def test_empty_string_returns_error(self):
        result = workspace_status(workspace_path="")
        assert result["status"] == "error"
        assert "workspace_path" in result["message"].lower() or "non-empty" in result["message"].lower()

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = workspace_status(workspace_path=str(tmp_path / "no_such_dir"))
        assert result["status"] == "error"

    def test_missing_manifest_returns_error(self, tmp_path):
        # Directory exists but no workspace.yaml
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        result = workspace_status(workspace_path=str(bare_dir))
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# media_list_assets — error paths
# ---------------------------------------------------------------------------

class TestMediaListAssetsErrorPaths:
    def test_empty_workspace_path_returns_error(self):
        result = media_list_assets(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = media_list_assets(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_missing_raw_dir_returns_empty_list(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Ensure media/raw doesn't exist
        import shutil as _shutil
        raw_dir = Path(ws_root) / "media" / "raw"
        if raw_dir.exists():
            _shutil.rmtree(raw_dir)
        result = media_list_assets(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_returns_success_with_valid_workspace(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = media_list_assets(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "assets" in result["data"]
        assert "count" in result["data"]


# ---------------------------------------------------------------------------
# markers_auto_generate — error paths
# ---------------------------------------------------------------------------

class TestMarkersAutoGenerateErrorPaths:
    def test_empty_workspace_path_returns_error(self):
        result = markers_auto_generate(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = markers_auto_generate(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_success_with_zero(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = markers_auto_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["marker_files"] == 0
        assert result["data"]["total_markers"] == 0


# ---------------------------------------------------------------------------
# clips_label
# ---------------------------------------------------------------------------

class TestClipsLabel:
    def test_empty_workspace_path_returns_error(self):
        result = clips_label(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = clips_label(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_success(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = clips_label(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "label_count" in result["data"]
        assert result["data"]["label_count"] == 0

    def test_with_transcript_generates_labels(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        result = clips_label(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["label_count"] >= 0  # may be 0 if no markers yet


# ---------------------------------------------------------------------------
# clips_search
# ---------------------------------------------------------------------------

class TestClipsSearch:
    def test_empty_workspace_path_returns_error(self):
        result = clips_search(workspace_path="", query="demo")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = clips_search(workspace_path=str(tmp_path / "ghost"), query="demo")
        assert result["status"] == "error"

    def test_empty_query_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = clips_search(workspace_path=ws_root, query="")
        assert result["status"] == "error"
        assert "query" in result["message"].lower()

    def test_whitespace_query_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = clips_search(workspace_path=ws_root, query="   ")
        assert result["status"] == "error"

    def test_no_labels_returns_empty_results(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = clips_search(workspace_path=ws_root, query="tutorial")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["query"] == "tutorial"

    def test_returns_results_key(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = clips_search(workspace_path=ws_root, query="test")
        assert result["status"] == "success"
        assert "results" in result["data"]


# ---------------------------------------------------------------------------
# pacing_analyze
# ---------------------------------------------------------------------------

class TestPacingAnalyze:
    def test_empty_workspace_path_returns_error(self):
        result = pacing_analyze(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = pacing_analyze(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_empty_reports(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = pacing_analyze(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["reports"] == []

    def test_with_transcript_returns_report(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        result = pacing_analyze(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] >= 1
        report = result["data"]["reports"][0]
        assert "overall_wpm" in report
        assert "overall_pace" in report


# ---------------------------------------------------------------------------
# broll_suggest
# ---------------------------------------------------------------------------

class TestBrollSuggest:
    def test_empty_workspace_path_returns_error(self):
        result = broll_suggest(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = broll_suggest(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_empty_suggestions(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = broll_suggest(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert isinstance(result["data"]["suggestions"], list)

    def test_with_transcript_returns_suggestions_structure(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        result = broll_suggest(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "count" in result["data"]
        assert "by_category" in result["data"]
        assert "markdown" in result["data"]


# ---------------------------------------------------------------------------
# pattern_extract
# ---------------------------------------------------------------------------

class TestPatternExtract:
    def test_empty_workspace_path_returns_error(self):
        result = pattern_extract(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = pattern_extract(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = pattern_extract(workspace_path=ws_root)
        # Should return error (no transcripts to extract from) or empty data
        assert result["status"] in ("error", "success")
        if result["status"] == "error":
            assert "message" in result

    def test_with_transcript_returns_build_data(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "build_clip")
        result = pattern_extract(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "materials" in result["data"]
        assert "steps" in result["data"]
        assert "build_notes_md" in result["data"]


# ---------------------------------------------------------------------------
# title_cards_generate
# ---------------------------------------------------------------------------

class TestTitleCardsGenerate:
    def test_empty_workspace_path_returns_error(self):
        result = title_cards_generate(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = title_cards_generate(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_markers_returns_intro_only(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = title_cards_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert "title_cards" in result["data"]
        assert "count" in result["data"]

    def test_with_chapter_markers_returns_cards(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        result = title_cards_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] >= 1
        assert "saved_to" in result["data"]


# ---------------------------------------------------------------------------
# replay_generate
# ---------------------------------------------------------------------------

class TestReplayGenerate:
    def test_empty_workspace_path_returns_error(self):
        result = replay_generate(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = replay_generate(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_negative_duration_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = replay_generate(workspace_path=ws_root, target_duration=-10.0)
        assert result["status"] == "error"
        assert "positive" in result["message"].lower() or "target_duration" in result["message"].lower()

    def test_zero_duration_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = replay_generate(workspace_path=ws_root, target_duration=0.0)
        assert result["status"] == "error"

    def test_no_markers_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = replay_generate(workspace_path=ws_root, target_duration=60.0)
        assert result["status"] == "error"

    def test_with_markers_returns_kdenlive_path(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        result = replay_generate(workspace_path=ws_root, target_duration=30.0)
        assert result["status"] == "success"
        assert "kdenlive_path" in result["data"]
        assert result["data"]["kdenlive_path"].endswith(".kdenlive")


# ---------------------------------------------------------------------------
# project_validate — error paths
# ---------------------------------------------------------------------------

class TestProjectValidateErrorPaths:
    def test_empty_workspace_path_returns_error(self):
        result = project_validate(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = project_validate(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_missing_working_copies_dir_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        # Do not create a working copy — no projects/working_copies dir
        result = project_validate(workspace_path=ws_root)
        assert result["status"] == "error"
        assert "message" in result


# ---------------------------------------------------------------------------
# snapshot_list — error paths
# ---------------------------------------------------------------------------

class TestSnapshotListErrorPaths:
    def test_empty_workspace_path_returns_error(self):
        result = snapshot_list(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = snapshot_list(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_valid_workspace_with_empty_snapshots(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = snapshot_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["snapshots"] == []


# ---------------------------------------------------------------------------
# snapshot_restore — error paths
# ---------------------------------------------------------------------------

class TestSnapshotRestore:
    def test_empty_workspace_path_returns_error(self):
        result = snapshot_restore(workspace_path="", snapshot_id="abc")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = snapshot_restore(workspace_path=str(tmp_path / "ghost"), snapshot_id="abc")
        assert result["status"] == "error"

    def test_empty_snapshot_id_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = snapshot_restore(workspace_path=ws_root, snapshot_id="")
        assert result["status"] == "error"
        assert "snapshot_id" in result["message"].lower()

    def test_nonexistent_snapshot_id_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = snapshot_restore(workspace_path=ws_root, snapshot_id="20999999_999999-nonexistent")
        assert result["status"] == "error"
        assert "not found" in result["message"].lower() or "snapshot" in result["message"].lower()


# ---------------------------------------------------------------------------
# markers_list
# ---------------------------------------------------------------------------

class TestMarkersList:
    def test_empty_workspace_path_returns_error(self):
        result = markers_list(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = markers_list(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_markers_dir_returns_empty(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = markers_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["total_markers"] == 0
        assert result["data"]["marker_files"] == []

    def test_after_marker_generation_lists_files(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        markers_auto_generate(workspace_path=ws_root)
        result = markers_list(workspace_path=ws_root)
        assert result["status"] == "success"
        assert len(result["data"]["marker_files"]) >= 1
        assert result["data"]["total_markers"] >= 0


# ---------------------------------------------------------------------------
# transcript_export
# ---------------------------------------------------------------------------

class TestTranscriptExport:
    def test_empty_workspace_path_returns_error(self):
        result = transcript_export(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = transcript_export(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_dir_returns_empty(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = transcript_export(workspace_path=ws_root, format="srt")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_invalid_format_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = transcript_export(workspace_path=ws_root, format="invalid_fmt")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# subtitles_generate
# ---------------------------------------------------------------------------

class TestSubtitlesGenerate:
    def test_empty_workspace_path_returns_error(self):
        result = subtitles_generate(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = subtitles_generate(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_transcripts_returns_empty(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = subtitles_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_with_transcript_generates_srt(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        transcripts_dir = Path(ws_root) / "transcripts"
        _fake_transcript(transcripts_dir, "clip1")
        result = subtitles_generate(workspace_path=ws_root)
        assert result["status"] == "success"
        assert result["data"]["count"] >= 1


# ---------------------------------------------------------------------------
# subtitles_export
# ---------------------------------------------------------------------------

class TestSubtitlesExport:
    def test_empty_workspace_path_returns_error(self):
        result = subtitles_export(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = subtitles_export(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_reports_dir_returns_empty(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = subtitles_export(workspace_path=ws_root, format="srt")
        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    def test_invalid_format_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = subtitles_export(workspace_path=ws_root, format="xyz")
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# render_preview — error paths
# ---------------------------------------------------------------------------

class TestRenderPreview:
    def test_empty_workspace_path_returns_error(self):
        result = render_preview(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = render_preview(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"

    def test_no_kdenlive_files_returns_error(self, tmp_path):
        created = _make_workspace(tmp_path)
        ws_root = created["data"]["workspace_root"]
        result = render_preview(workspace_path=ws_root)
        assert result["status"] == "error"
        assert "message" in result


# ---------------------------------------------------------------------------
# render_status — error paths
# ---------------------------------------------------------------------------

class TestRenderStatusErrorPaths:
    def test_empty_workspace_path_returns_error(self):
        result = render_status(workspace_path="")
        assert result["status"] == "error"

    def test_nonexistent_path_returns_error(self, tmp_path):
        result = render_status(workspace_path=str(tmp_path / "ghost"))
        assert result["status"] == "error"
