"""Unit tests for core data models: serialize/deserialize round-trips."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from workshop_video_brain.core.models import (
    AnalysisStatus,
    JobStatus,
    Marker,
    MarkerCategory,
    MediaAsset,
    ProjectStatus,
    ProxyStatus,
    ShotType,
    Transcript,
    TranscriptSegment,
    ValidationSeverity,
    VideoProject,
    Workspace,
    WordTiming,
)


# ---------------------------------------------------------------------------
# MediaAsset
# ---------------------------------------------------------------------------

def _make_media_asset() -> MediaAsset:
    return MediaAsset(
        path="/media/raw/clip.mp4",
        relative_path="media/raw/clip.mp4",
        media_type="video",
        container="mp4",
        duration=120.5,
        fps=25.0,
        width=1920,
        height=1080,
        proxy_status=ProxyStatus.pending,
        transcript_status="completed",
        analysis_status=AnalysisStatus.pending,
    )


class TestMediaAsset:
    def test_json_round_trip(self):
        asset = _make_media_asset()
        restored = MediaAsset.from_json(asset.to_json())
        assert restored.path == asset.path
        assert restored.id == asset.id
        assert restored.fps == asset.fps

    def test_yaml_round_trip(self):
        asset = _make_media_asset()
        restored = MediaAsset.from_yaml(asset.to_yaml())
        assert restored.width == asset.width
        assert restored.height == asset.height
        assert restored.proxy_status == ProxyStatus.pending.value

    def test_enum_values_stored_as_strings(self):
        asset = _make_media_asset()
        data = json.loads(asset.to_json())
        assert data["proxy_status"] == "pending"
        assert data["transcript_status"] == "completed"

    def test_enum_coverage(self):
        for member in ProxyStatus:
            a = MediaAsset(path="/x", proxy_status=member)
            assert a.proxy_status == member.value


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------

def _make_transcript() -> Transcript:
    asset_id = uuid4()
    return Transcript(
        asset_id=asset_id,
        engine="whisper",
        model="small",
        language="en",
        raw_text="Hello world",
        segments=[
            TranscriptSegment(
                start_seconds=0.0,
                end_seconds=2.5,
                text="Hello world",
                words=[WordTiming(word="Hello", start=0.0, end=0.5)],
            )
        ],
    )


class TestTranscript:
    def test_json_round_trip(self):
        t = _make_transcript()
        restored = Transcript.from_json(t.to_json())
        assert restored.raw_text == t.raw_text
        assert len(restored.segments) == 1
        assert restored.segments[0].words[0].word == "Hello"

    def test_yaml_round_trip(self):
        t = _make_transcript()
        restored = Transcript.from_yaml(t.to_yaml())
        assert restored.engine == "whisper"
        assert restored.segments[0].end_seconds == 2.5


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------

def _make_marker() -> Marker:
    return Marker(
        category=MarkerCategory.important_caution,
        confidence_score=0.9,
        source_method="llm",
        reason="Safety step",
        start_seconds=10.0,
        end_seconds=15.0,
    )


class TestMarker:
    def test_json_round_trip(self):
        m = _make_marker()
        restored = Marker.from_json(m.to_json())
        assert restored.category == MarkerCategory.important_caution.value
        assert restored.confidence_score == 0.9

    def test_yaml_round_trip(self):
        m = _make_marker()
        restored = Marker.from_yaml(m.to_yaml())
        assert restored.start_seconds == 10.0

    def test_all_marker_categories(self):
        for cat in MarkerCategory:
            mk = Marker(category=cat, confidence_score=0.5)
            assert mk.category == cat.value


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

def _make_workspace() -> Workspace:
    project = VideoProject(
        title="My Project",
        slug="my-project",
        status=ProjectStatus.editing,
    )
    return Workspace(
        project=project,
        media_root="/media",
        workspace_root="/ws/my-project",
    )


class TestWorkspace:
    def test_json_round_trip(self):
        ws = _make_workspace()
        restored = Workspace.from_json(ws.to_json())
        assert restored.project.title == "My Project"
        assert restored.project.status == ProjectStatus.editing.value

    def test_yaml_round_trip(self):
        ws = _make_workspace()
        restored = Workspace.from_yaml(ws.to_yaml())
        assert restored.media_root == "/media"

    def test_project_status_enum_coverage(self):
        for status in ProjectStatus:
            vp = VideoProject(title="t", status=status)
            assert vp.status == status.value

    def test_job_status_enum_coverage(self):
        for status in JobStatus:
            assert status.value  # just ensure all members are accessible

    def test_validation_severity_coverage(self):
        for sev in ValidationSeverity:
            assert sev.value

    def test_shot_type_coverage(self):
        for st in ShotType:
            assert st.value
