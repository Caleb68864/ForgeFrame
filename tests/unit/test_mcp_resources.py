"""Tests for workshop_video_brain.edit_mcp.server.resources."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from workshop_video_brain.workspace.manifest import WorkspaceManifest, write_manifest
from workshop_video_brain.workspace.folders import create_workspace_structure
from workshop_video_brain.edit_mcp.server.resources import (
    workspace_current_summary,
    workspace_media_catalog,
    workspace_transcript_index,
    workspace_markers,
    workspace_timeline_summary,
    workspace_render_logs,
    system_capabilities,
    _workspace_summary_text,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _seed_workspace(tmp_path: Path, title: str = "Test Project") -> Path:
    ws = tmp_path / "workspace"
    create_workspace_structure(ws)
    manifest = WorkspaceManifest(project_title=title, slug="test-project", media_root=str(ws))
    write_manifest(ws, manifest)
    return ws


# ---------------------------------------------------------------------------
# _workspace_summary_text
# ---------------------------------------------------------------------------

class TestWorkspaceSummaryText:
    def test_returns_error_string_when_no_manifest(self, tmp_path: Path):
        result = _workspace_summary_text(str(tmp_path))
        assert "No workspace.yaml" in result

    def test_returns_formatted_markdown_when_manifest_present(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path, "My Video")
        result = _workspace_summary_text(str(ws))
        assert "# Workspace" in result
        assert "My Video" in result

    def test_returns_string_type(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        result = _workspace_summary_text(str(ws))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# workspace_current_summary
# ---------------------------------------------------------------------------

class TestWorkspaceCurrentSummary:
    def test_returns_string(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        with patch.dict(os.environ, {"WVB_WORKSPACE_ROOT": str(ws)}):
            result = workspace_current_summary()
        assert isinstance(result, str)

    def test_uses_env_var(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path, "EnvTest")
        with patch.dict(os.environ, {"WVB_WORKSPACE_ROOT": str(ws)}):
            result = workspace_current_summary()
        assert "EnvTest" in result

    def test_fallback_when_no_env_var(self, tmp_path: Path):
        env = {k: v for k, v in os.environ.items() if k != "WVB_WORKSPACE_ROOT"}
        with patch.dict(os.environ, env, clear=True):
            result = workspace_current_summary()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# workspace_media_catalog
# ---------------------------------------------------------------------------

class TestWorkspaceMediaCatalog:
    def test_returns_error_string_when_no_raw_dir(self, tmp_path: Path):
        result = workspace_media_catalog(str(tmp_path))
        assert "No media/raw" in result

    def test_returns_string_type(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.scan_directory",
            return_value=[],
        ):
            result = workspace_media_catalog(str(ws))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# workspace_transcript_index
# ---------------------------------------------------------------------------

class TestWorkspaceTranscriptIndex:
    def test_returns_error_when_no_transcripts_dir(self, tmp_path: Path):
        result = workspace_transcript_index(str(tmp_path))
        assert "No transcripts/" in result

    def test_returns_no_transcripts_message_when_dir_empty(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        result = workspace_transcript_index(str(ws))
        assert "No transcripts found" in result

    def test_returns_string_type(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        result = workspace_transcript_index(str(ws))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# workspace_markers
# ---------------------------------------------------------------------------

class TestWorkspaceMarkers:
    def test_returns_error_when_no_markers_dir(self, tmp_path: Path):
        result = workspace_markers(str(tmp_path))
        assert "No markers/" in result

    def test_returns_no_files_message_when_dir_empty(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        result = workspace_markers(str(ws))
        assert "No marker files found" in result

    def test_parses_marker_json_file(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        marker_data = [
            {"start_seconds": 1.0, "end_seconds": 2.0, "category": "hook_candidate",
             "confidence_score": 0.9, "reason": "Strong opening"},
        ]
        (ws / "markers" / "clip01_markers.json").write_text(
            json.dumps(marker_data), encoding="utf-8"
        )
        result = workspace_markers(str(ws))
        assert "hook_candidate" in result
        assert "Total markers: 1" in result


# ---------------------------------------------------------------------------
# workspace_timeline_summary
# ---------------------------------------------------------------------------

class TestWorkspaceTimelineSummary:
    def test_returns_error_when_no_working_copies_dir(self, tmp_path: Path):
        result = workspace_timeline_summary(str(tmp_path))
        assert "No projects/working_copies/" in result

    def test_returns_no_timeline_message_when_dir_empty(self, tmp_path: Path):
        ws = _seed_workspace(tmp_path)
        result = workspace_timeline_summary(str(ws))
        assert "No timeline files found" in result


# ---------------------------------------------------------------------------
# workspace_render_logs
# ---------------------------------------------------------------------------

class TestWorkspaceRenderLogs:
    def test_returns_string_when_no_jobs(self, tmp_path: Path):
        with patch(
            "workshop_video_brain.edit_mcp.pipelines.render_pipeline.list_renders",
            return_value=[],
        ):
            result = workspace_render_logs(str(tmp_path))
        assert "No render jobs found" in result

    def test_returns_string_type(self, tmp_path: Path):
        with patch(
            "workshop_video_brain.edit_mcp.pipelines.render_pipeline.list_renders",
            return_value=[],
        ):
            result = workspace_render_logs(str(tmp_path))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# system_capabilities
# ---------------------------------------------------------------------------

class TestSystemCapabilities:
    def test_returns_string(self):
        result = system_capabilities()
        assert isinstance(result, str)

    def test_contains_ffmpeg_status(self):
        result = system_capabilities()
        assert "FFmpeg" in result

    def test_contains_melt_status(self):
        result = system_capabilities()
        assert "melt" in result

    def test_contains_available_tools_section(self):
        result = system_capabilities()
        assert "Available MCP Tools" in result

    def test_contains_mcp_resources_section(self):
        result = system_capabilities()
        assert "MCP Resources" in result

    def test_contains_workspace_create_tool(self):
        result = system_capabilities()
        assert "workspace_create" in result

    def test_ffmpeg_reports_available_or_not_found(self):
        result = system_capabilities()
        assert "available" in result or "NOT FOUND" in result
