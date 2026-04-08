"""Unit tests for the Kdenlive project validator."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project


def _base_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Valid Project",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(id="prod0", resource="/media/clip.mp4", properties={"resource": "/media/clip.mp4"})
        ],
        playlists=[
            Playlist(id="pl0", entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)])
        ],
        tracks=[Track(id="pl0", track_type="video")],
    )


class TestValidatorCleanProject:
    def test_clean_project_no_errors(self):
        project = _base_project()
        report = validate_project(project)
        errors = [i for i in report.items if i.severity in (
            ValidationSeverity.error.value,
            ValidationSeverity.blocking_error.value,
        )]
        assert errors == []

    def test_summary_no_issues(self):
        project = _base_project()
        report = validate_project(project)
        assert "No issues found" in report.summary


class TestValidatorProfileChecks:
    def test_invalid_width_is_blocking_error(self):
        project = _base_project()
        project.profile.width = 0
        report = validate_project(project)
        severities = [i.severity for i in report.items]
        assert ValidationSeverity.blocking_error.value in severities

    def test_invalid_height_is_blocking_error(self):
        project = _base_project()
        project.profile.height = -1
        report = validate_project(project)
        severities = [i.severity for i in report.items]
        assert ValidationSeverity.blocking_error.value in severities

    def test_invalid_fps_is_error(self):
        project = _base_project()
        project.profile.fps = 0.0
        report = validate_project(project)
        severities = [i.severity for i in report.items]
        assert ValidationSeverity.error.value in severities


class TestValidatorTrackChecks:
    def test_no_tracks_is_warning(self):
        project = _base_project()
        project.tracks = []
        report = validate_project(project)
        cats = [i.category for i in report.items]
        assert "tracks" in cats


class TestValidatorMediaChecks:
    def test_missing_media_file_is_error(self, tmp_path):
        project = _base_project()
        # workspace_root provided but file doesn't exist
        report = validate_project(project, workspace_root=tmp_path)
        errors = [i for i in report.items if i.severity == ValidationSeverity.error.value]
        media_errors = [e for e in errors if e.category == "media"]
        assert len(media_errors) >= 1

    def test_existing_media_file_no_error(self, tmp_path):
        media_file = tmp_path / "clip.mp4"
        media_file.touch()
        project = _base_project()
        project.producers[0].resource = str(media_file)
        project.producers[0].properties["resource"] = str(media_file)
        report = validate_project(project, workspace_root=tmp_path)
        media_errors = [i for i in report.items if i.category == "media"]
        assert media_errors == []

    def test_empty_resource_is_warning(self, tmp_path):
        project = _base_project()
        project.producers[0].resource = ""
        project.producers[0].properties["resource"] = ""
        report = validate_project(project, workspace_root=tmp_path)
        warnings = [i for i in report.items if i.category == "media" and i.severity == ValidationSeverity.warning.value]
        assert len(warnings) >= 1


class TestValidatorPlaylistChecks:
    def test_unknown_producer_in_playlist_is_error(self):
        project = _base_project()
        project.playlists[0].entries[0].producer_id = "nonexistent_producer"
        report = validate_project(project)
        errors = [i for i in report.items if i.category == "playlist"]
        assert len(errors) >= 1

    def test_in_greater_than_out_is_warning(self):
        project = _base_project()
        project.playlists[0].entries[0].in_point = 100
        project.playlists[0].entries[0].out_point = 50
        report = validate_project(project)
        warnings = [i for i in report.items if i.category == "playlist" and i.severity == ValidationSeverity.warning.value]
        assert len(warnings) >= 1


class TestValidatorGuideChecks:
    def test_negative_guide_position_is_warning(self):
        project = _base_project()
        project.guides.append(Guide(position=-1, label="Bad guide"))
        report = validate_project(project)
        guide_warnings = [i for i in report.items if i.category == "guides"]
        assert len(guide_warnings) >= 1

    def test_valid_guide_no_warning(self):
        project = _base_project()
        project.guides.append(Guide(position=100, label="Good guide"))
        report = validate_project(project)
        guide_warnings = [i for i in report.items if i.category == "guides"]
        assert guide_warnings == []


class TestValidatorSummary:
    def test_summary_mentions_issue_counts(self):
        project = _base_project()
        project.profile.width = 0  # blocking_error
        project.tracks = []  # warning
        report = validate_project(project)
        assert len(report.summary) > 0
        assert "Validation issues:" in report.summary
