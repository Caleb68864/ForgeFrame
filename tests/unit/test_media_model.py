"""Tests for MediaAsset field defaults, aliases, and enum handling (MD-05)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.media import MediaAsset


def test_media_asset_required():
    with pytest.raises(ValidationError):
        MediaAsset()  # type: ignore[call-arg]


def test_media_asset_defaults():
    a = MediaAsset(path="/footage/clip.mp4")
    assert a.duration == 0.0
    assert a.duration_seconds == 0.0
    assert a.fps == 0.0
    assert a.width == 0
    assert a.height == 0
    assert a.file_size == 0
    assert a.file_size_bytes == 0
    assert a.hash == ""
    assert a.proxy_path == ""


def test_media_asset_status_defaults():
    a = MediaAsset(path="/footage/clip.mp4")
    assert a.proxy_status == "not_needed"
    assert a.transcript_status == "pending"
    assert a.analysis_status == "pending"
    assert isinstance(a.proxy_status, str)
    assert isinstance(a.transcript_status, str)
    assert isinstance(a.analysis_status, str)


def test_media_asset_id_auto_generated():
    a1 = MediaAsset(path="/footage/a.mp4")
    a2 = MediaAsset(path="/footage/b.mp4")
    assert a1.id != a2.id


def test_media_asset_created_at_utc():
    import datetime
    a = MediaAsset(path="/footage/clip.mp4")
    assert a.created_at.tzinfo is not None


def test_media_asset_duration_alias():
    a = MediaAsset(path="/footage/clip.mp4", duration=5.0)
    assert a.duration == 5.0
    assert a.duration_seconds == 0.0  # independent field


def test_media_asset_file_size_alias():
    a = MediaAsset(path="/footage/clip.mp4", file_size=1024)
    assert a.file_size == 1024
    assert a.file_size_bytes == 0  # independent field


def test_media_asset_both_aliases_set():
    a = MediaAsset(path="/footage/clip.mp4", duration=5.0, duration_seconds=5.0)
    d = a.model_dump()
    assert d["duration"] == 5.0
    assert d["duration_seconds"] == 5.0


def test_media_asset_color_fields_none():
    a = MediaAsset(path="/footage/clip.mp4")
    assert a.color_space is None
    assert a.color_primaries is None
    assert a.color_transfer is None


def test_media_asset_color_fields_set():
    a = MediaAsset(
        path="/footage/clip.mp4",
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
    )
    d = a.model_dump()
    assert d["color_space"] == "bt709"
    assert d["color_primaries"] == "bt709"
    assert d["color_transfer"] == "bt709"


def test_media_asset_is_vfr():
    a = MediaAsset(path="/footage/clip.mp4")
    assert a.is_vfr is False
    a2 = MediaAsset(path="/footage/clip.mp4", is_vfr=True)
    d = a2.model_dump()
    assert d["is_vfr"] is True


def test_media_asset_all_fields():
    import datetime
    a = MediaAsset(
        path="/footage/clip.mp4",
        relative_path="footage/clip.mp4",
        media_type="video",
        container="mp4",
        video_codec="h264",
        audio_codec="aac",
        duration=10.0,
        duration_seconds=10.0,
        fps=29.97,
        width=1920,
        height=1080,
        aspect_ratio="16:9",
        channels=2,
        sample_rate=48000,
        bitrate=8000000,
        file_size=100000000,
        file_size_bytes=100000000,
        hash="abc123",
        proxy_path="/proxy/clip.mp4",
        proxy_status="ready",
        transcript_status="completed",
        analysis_status="completed",
        is_vfr=False,
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
    )
    d = a.model_dump()
    assert d["path"] == "/footage/clip.mp4"
    assert d["width"] == 1920


def test_media_asset_json_round_trip():
    a = MediaAsset(path="/footage/clip.mp4", duration=5.5, width=1920)
    a2 = MediaAsset.from_json(a.to_json())
    assert a2 == a


def test_media_asset_yaml_round_trip():
    a = MediaAsset(path="/footage/clip.mp4", hash="deadbeef")
    a2 = MediaAsset.from_yaml(a.to_yaml())
    assert a2 == a


def test_media_asset_invalid_proxy_status():
    with pytest.raises(ValidationError):
        MediaAsset(path="/footage/clip.mp4", proxy_status="invalid_status")


def test_media_asset_invalid_type():
    # Pydantic v2 rejects int for str fields
    with pytest.raises(ValidationError):
        MediaAsset(path=123)  # type: ignore[arg-type]
