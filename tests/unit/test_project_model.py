"""Tests for VideoProject, RenderJob, SnapshotRecord (MD-10)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.project import RenderJob, SnapshotRecord, VideoProject


# ---------------------------------------------------------------------------
# VideoProject
# ---------------------------------------------------------------------------

def test_video_project_required():
    with pytest.raises(ValidationError):
        VideoProject()  # type: ignore[call-arg]


def test_video_project_defaults():
    vp = VideoProject(title="My Build")
    assert vp.slug == ""
    assert vp.status == "idea"
    assert vp.content_type == ""


def test_video_project_id_auto_generated():
    vp1 = VideoProject(title="A")
    vp2 = VideoProject(title="B")
    assert vp1.id != vp2.id


def test_video_project_created_at_utc():
    vp = VideoProject(title="Test")
    assert vp.created_at.tzinfo is not None


def test_video_project_updated_at_utc():
    vp = VideoProject(title="Test")
    assert vp.updated_at.tzinfo is not None


def test_video_project_status_enum():
    vp = VideoProject(title="Test")
    assert isinstance(vp.status, str)
    assert vp.status == "idea"


def test_video_project_status_transition():
    vp = VideoProject(title="Test", status="published")
    assert vp.status == "published"


def test_video_project_invalid_status():
    with pytest.raises(ValidationError):
        VideoProject(title="Test", status="not_a_status")


def test_video_project_all_fields():
    vp = VideoProject(
        title="Backpack Build",
        slug="backpack-build",
        status="editing",
        content_type="tutorial",
    )
    d = vp.model_dump()
    assert d["title"] == "Backpack Build"
    assert d["slug"] == "backpack-build"
    assert d["status"] == "editing"


def test_video_project_json_round_trip():
    vp = VideoProject(title="Round Trip Test", slug="rtt", status="scripting")
    vp2 = VideoProject.from_json(vp.to_json())
    assert vp2 == vp


def test_video_project_yaml_round_trip():
    vp = VideoProject(title="YAML Test", status="filming")
    vp2 = VideoProject.from_yaml(vp.to_yaml())
    assert vp2 == vp


# ---------------------------------------------------------------------------
# RenderJob
# ---------------------------------------------------------------------------

def test_render_job_required():
    with pytest.raises(ValidationError):
        RenderJob()  # type: ignore[call-arg]

    ws_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        RenderJob(workspace_id=ws_id)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        RenderJob(project_path="/projects/test.kdenlive")  # type: ignore[call-arg]


def test_render_job_defaults():
    ws_id = uuid.uuid4()
    rj = RenderJob(workspace_id=ws_id, project_path="/projects/test.kdenlive")
    assert rj.profile == ""
    assert rj.output_path == ""
    assert rj.mode == ""
    assert rj.status == "queued"
    assert rj.started_at is None
    assert rj.completed_at is None
    assert rj.log_path == ""


def test_render_job_status_enum():
    ws_id = uuid.uuid4()
    rj = RenderJob(workspace_id=ws_id, project_path="/projects/test.kdenlive")
    assert isinstance(rj.status, str)
    assert rj.status == "queued"


def test_render_job_started_at_none():
    ws_id = uuid.uuid4()
    rj = RenderJob(workspace_id=ws_id, project_path="/projects/test.kdenlive")
    d = rj.model_dump()
    assert d["started_at"] is None


def test_render_job_timestamps_set():
    ws_id = uuid.uuid4()
    rj = RenderJob(
        workspace_id=ws_id,
        project_path="/projects/test.kdenlive",
        started_at="2026-04-09T10:00:00+00:00",
        completed_at="2026-04-09T10:05:00+00:00",
    )
    assert rj.started_at is not None
    assert rj.completed_at is not None
    assert rj.started_at.tzinfo is not None


def test_render_job_json_round_trip():
    ws_id = uuid.uuid4()
    rj = RenderJob(
        workspace_id=ws_id,
        project_path="/projects/test.kdenlive",
        profile="h264",
        status="running",
    )
    rj2 = RenderJob.from_json(rj.to_json())
    assert rj2 == rj


# ---------------------------------------------------------------------------
# SnapshotRecord
# ---------------------------------------------------------------------------

def test_snapshot_record_required():
    with pytest.raises(ValidationError):
        SnapshotRecord()  # type: ignore[call-arg]


def test_snapshot_record_defaults():
    ws_id = uuid.uuid4()
    sr = SnapshotRecord(workspace_id=ws_id)
    assert sr.project_file_path == ""
    assert sr.manifest_snapshot == {}
    assert sr.description == ""


def test_snapshot_record_timestamp_utc():
    ws_id = uuid.uuid4()
    sr = SnapshotRecord(workspace_id=ws_id)
    assert sr.timestamp.tzinfo is not None


def test_snapshot_record_manifest_snapshot():
    ws_id = uuid.uuid4()
    sr = SnapshotRecord(
        workspace_id=ws_id,
        manifest_snapshot={"media/clip.mp4": "abc123", "count": 5},
    )
    sr2 = SnapshotRecord.from_json(sr.to_json())
    assert sr2.manifest_snapshot["media/clip.mp4"] == "abc123"


def test_snapshot_record_yaml_round_trip():
    ws_id = uuid.uuid4()
    sr = SnapshotRecord(
        workspace_id=ws_id,
        project_file_path="/projects/test.kdenlive",
        description="Before render",
    )
    sr2 = SnapshotRecord.from_yaml(sr.to_yaml())
    assert sr2 == sr
