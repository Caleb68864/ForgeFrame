"""Tests for enum values, string comparison, and serialization (MD-02)."""
from __future__ import annotations

import json

import pytest
from workshop_video_brain.core.models.enums import (
    AnalysisStatus,
    JobStatus,
    MarkerCategory,
    ProjectStatus,
    ProxyStatus,
    TranscriptStatus,
    ValidationSeverity,
    ShotType,
)


@pytest.mark.parametrize("member,value", [
    (ProjectStatus.idea, "idea"),
    (ProjectStatus.outlining, "outlining"),
    (ProjectStatus.scripting, "scripting"),
    (ProjectStatus.filming, "filming"),
    (ProjectStatus.ingesting, "ingesting"),
    (ProjectStatus.editing, "editing"),
    (ProjectStatus.review, "review"),
    (ProjectStatus.rendering, "rendering"),
    (ProjectStatus.published, "published"),
    (ProjectStatus.archived, "archived"),
])
def test_project_status_values(member, value):
    assert member.value == value
    assert member == value


def test_project_status_count():
    assert len(ProjectStatus) == 10


@pytest.mark.parametrize("member,value", [
    (MarkerCategory.intro_candidate, "intro_candidate"),
    (MarkerCategory.hook_candidate, "hook_candidate"),
    (MarkerCategory.materials_mention, "materials_mention"),
    (MarkerCategory.step_explanation, "step_explanation"),
    (MarkerCategory.measurement_detail, "measurement_detail"),
    (MarkerCategory.important_caution, "important_caution"),
    (MarkerCategory.mistake_problem, "mistake_problem"),
    (MarkerCategory.fix_recovery, "fix_recovery"),
    (MarkerCategory.broll_candidate, "broll_candidate"),
    (MarkerCategory.closeup_needed, "closeup_needed"),
    (MarkerCategory.dead_air, "dead_air"),
    (MarkerCategory.repetition, "repetition"),
    (MarkerCategory.ending_reveal, "ending_reveal"),
    (MarkerCategory.chapter_candidate, "chapter_candidate"),
])
def test_marker_category_values(member, value):
    assert member.value == value
    assert member == value


def test_marker_category_count():
    assert len(MarkerCategory) == 14


@pytest.mark.parametrize("member,value", [
    (JobStatus.queued, "queued"),
    (JobStatus.running, "running"),
    (JobStatus.succeeded, "succeeded"),
    (JobStatus.failed, "failed"),
    (JobStatus.cancelled, "cancelled"),
])
def test_job_status_values(member, value):
    assert member.value == value
    assert member == value


def test_job_status_count():
    assert len(JobStatus) == 5


@pytest.mark.parametrize("member,value", [
    (ShotType.a_roll, "a_roll"),
    (ShotType.overhead, "overhead"),
    (ShotType.closeup, "closeup"),
    (ShotType.measurement, "measurement"),
    (ShotType.insert, "insert"),
    (ShotType.glamour, "glamour"),
    (ShotType.pickup, "pickup"),
])
def test_shot_type_values(member, value):
    assert member.value == value
    assert member == value


def test_shot_type_count():
    assert len(ShotType) == 7


@pytest.mark.parametrize("member,value", [
    (ProxyStatus.not_needed, "not_needed"),
    (ProxyStatus.pending, "pending"),
    (ProxyStatus.generating, "generating"),
    (ProxyStatus.ready, "ready"),
    (ProxyStatus.failed, "failed"),
])
def test_proxy_status_values(member, value):
    assert member.value == value
    assert member == value


def test_proxy_status_count():
    assert len(ProxyStatus) == 5


@pytest.mark.parametrize("member,value", [
    (TranscriptStatus.pending, "pending"),
    (TranscriptStatus.processing, "processing"),
    (TranscriptStatus.completed, "completed"),
    (TranscriptStatus.failed, "failed"),
])
def test_transcript_status_values(member, value):
    assert member.value == value
    assert member == value


def test_transcript_status_count():
    assert len(TranscriptStatus) == 4


@pytest.mark.parametrize("member,value", [
    (AnalysisStatus.pending, "pending"),
    (AnalysisStatus.processing, "processing"),
    (AnalysisStatus.completed, "completed"),
    (AnalysisStatus.failed, "failed"),
])
def test_analysis_status_values(member, value):
    assert member.value == value
    assert member == value


def test_analysis_status_count():
    assert len(AnalysisStatus) == 4


@pytest.mark.parametrize("member,value", [
    (ValidationSeverity.info, "info"),
    (ValidationSeverity.warning, "warning"),
    (ValidationSeverity.error, "error"),
    (ValidationSeverity.blocking_error, "blocking_error"),
])
def test_validation_severity_values(member, value):
    assert member.value == value
    assert member == value


def test_validation_severity_count():
    assert len(ValidationSeverity) == 4


def test_str_comparison():
    assert ProjectStatus.idea == "idea"
    assert JobStatus.queued == "queued"
    assert MarkerCategory.intro_candidate == "intro_candidate"
    assert ValidationSeverity.blocking_error == "blocking_error"


def test_str_inheritance():
    assert isinstance(ProjectStatus.published, str)
    assert isinstance(MarkerCategory.dead_air, str)
    assert isinstance(JobStatus.succeeded, str)
    assert isinstance(ShotType.a_roll, str)
    assert isinstance(ProxyStatus.ready, str)
    assert isinstance(TranscriptStatus.completed, str)
    assert isinstance(AnalysisStatus.failed, str)
    assert isinstance(ValidationSeverity.error, str)


def test_invalid_member():
    with pytest.raises(ValueError):
        ProjectStatus("bogus")


def test_json_serializable():
    result = json.dumps(ProjectStatus.idea)
    assert result == '"idea"'

    result = json.dumps(ValidationSeverity.blocking_error)
    assert result == '"blocking_error"'
