"""Unit tests for the read-only research_media MCP tools.

Exercises the four tools against the checked-in greenscreen fixture
(~20s, 1280x720). Frame-extraction / scene-detect tests are gated on
ffmpeg/ffprobe availability; error-path tests use monkeypatching so they
run without any external binary.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegNotFound
from workshop_video_brain.edit_mcp.server.tools import research_media

from tests._testkit import call_tool as _invoke
from tests._testkit import requires_ffmpeg_ffprobe

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "media_generated"
    / "greenscreen_reporter_720.mp4"
)


class TestResearchProbeVideo:
    @requires_ffmpeg_ffprobe
    def test_probes_fixture(self):
        result = _invoke(research_media.research_probe_video, video_path=str(FIXTURE))
        assert result["status"] == "success"
        assert result["data"]["duration_seconds"] > 0

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "does_not_exist.mp4"
        result = _invoke(research_media.research_probe_video, video_path=str(missing))
        assert result["status"] == "error"
        assert result["error_type"] == "missing_file"


class TestResearchExtractFrame:
    @requires_ffmpeg_ffprobe
    def test_extracts_frame_at_timestamp(self, tmp_path):
        out = tmp_path / "frame.png"
        result = _invoke(
            research_media.research_extract_frame,
            video_path=str(FIXTURE),
            timestamp_seconds=1.0,
            output_path=str(out),
        )
        assert result["status"] == "success"
        assert out.exists()
        assert out.stat().st_size > 0
        actual = result["data"]["actual_timestamp_seconds"]
        assert abs(actual - 1.0) <= 0.05

    @requires_ffmpeg_ffprobe
    def test_clamps_timestamp_past_eof(self, tmp_path):
        out = tmp_path / "frame_eof.png"
        result = _invoke(
            research_media.research_extract_frame,
            video_path=str(FIXTURE),
            timestamp_seconds=10000.0,
            output_path=str(out),
        )
        assert result["status"] == "success"
        assert out.exists()
        actual = result["data"]["actual_timestamp_seconds"]
        assert actual < 10000.0
        assert actual <= 20.02


class TestResearchExtractFrameBurst:
    @requires_ffmpeg_ffprobe
    def test_burst_returns_frames(self):
        result = _invoke(
            research_media.research_extract_frame_burst,
            video_path=str(FIXTURE),
            start_seconds=0.0,
            end_seconds=2.0,
            interval_seconds=0.5,
            max_frames=20,
        )
        assert result["status"] == "success"
        assert result["data"]["count"] > 0
        assert len(result["data"]["frames"]) == result["data"]["count"]


class TestResearchDetectScenes:
    @requires_ffmpeg_ffprobe
    def test_detects_scenes_on_fixture(self):
        result = _invoke(
            research_media.research_detect_scenes,
            video_path=str(FIXTURE),
        )
        assert result["status"] == "success"
        assert isinstance(result["data"]["scenes"], list)

    def test_missing_binary_on_ffmpeg_absent(self):
        # detect_scene_changes is imported locally inside the tool body, so
        # patch it at its adapter-module source rather than on research_media.
        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.scene.detect_scene_changes",
            side_effect=FFmpegNotFound("ffmpeg not found"),
        ):
            result = _invoke(
                research_media.research_detect_scenes,
                video_path=str(FIXTURE),
            )
        assert result["status"] == "error"
        assert result["error_type"] == "missing_binary"
