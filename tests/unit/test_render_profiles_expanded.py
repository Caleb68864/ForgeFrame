"""Tests for expanded render profiles and codec availability check."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    load_profile,
    list_profiles,
)
from workshop_video_brain.edit_mcp.adapters.render.executor import check_codec_available


# ---------------------------------------------------------------------------
# Profile directory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def profiles_dir(tmp_path):
    """Create a temporary profiles directory with all expected profiles."""
    profiles = {
        "youtube-1080p": {
            "name": "youtube-1080p",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "libx264",
            "video_bitrate": "8M",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "extra_args": ["-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        },
        "youtube-4k": {
            "name": "youtube-4k",
            "width": 3840,
            "height": 2160,
            "fps": 30,
            "video_codec": "libx264",
            "video_bitrate": "35M",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "extra_args": ["-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        },
        "vimeo-hq": {
            "name": "vimeo-hq",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "prores_ks",
            "video_bitrate": "0",
            "audio_codec": "aac",
            "audio_bitrate": "320k",
            "extra_args": ["-profile:v", "3", "-pix_fmt", "yuv422p10le"],
        },
        "master-prores": {
            "name": "master-prores",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "prores_ks",
            "video_bitrate": "0",
            "audio_codec": "pcm_s24le",
            "audio_bitrate": "0",
            "extra_args": ["-profile:v", "3", "-pix_fmt", "yuv422p10le"],
        },
        "master-dnxhr": {
            "name": "master-dnxhr",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "dnxhd",
            "video_bitrate": "0",
            "audio_codec": "pcm_s24le",
            "audio_bitrate": "0",
            "extra_args": ["-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le"],
        },
    }
    import yaml
    for name, data in profiles.items():
        (tmp_path / f"{name}.yaml").write_text(
            yaml.dump(data, default_flow_style=False), encoding="utf-8"
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Profile loading tests
# ---------------------------------------------------------------------------

class TestYouTube1080pProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("youtube-1080p", profiles_dir=profiles_dir)

        assert profile.name == "youtube-1080p"
        assert profile.width == 1920
        assert profile.height == 1080
        assert profile.fps == 30
        assert profile.video_codec == "libx264"
        assert profile.video_bitrate == "8M"
        assert profile.audio_codec == "aac"
        assert profile.audio_bitrate == "192k"
        assert "-movflags" in profile.extra_args
        assert "+faststart" in profile.extra_args

    def test_has_h264_high_profile(self, profiles_dir):
        profile = load_profile("youtube-1080p", profiles_dir=profiles_dir)
        assert "-profile:v" in profile.extra_args
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "high"


class TestYouTube4kProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("youtube-4k", profiles_dir=profiles_dir)

        assert profile.name == "youtube-4k"
        assert profile.width == 3840
        assert profile.height == 2160
        assert profile.video_bitrate == "35M"

    def test_has_faststart(self, profiles_dir):
        profile = load_profile("youtube-4k", profiles_dir=profiles_dir)
        assert "+faststart" in profile.extra_args


class TestVimeoHQProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("vimeo-hq", profiles_dir=profiles_dir)

        assert profile.name == "vimeo-hq"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_bitrate == "320k"

    def test_uses_prores_profile_3(self, profiles_dir):
        profile = load_profile("vimeo-hq", profiles_dir=profiles_dir)
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "3"


class TestMasterProResProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("master-prores", profiles_dir=profiles_dir)

        assert profile.name == "master-prores"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_codec == "pcm_s24le"
        assert profile.video_bitrate == "0"
        assert profile.audio_bitrate == "0"

    def test_uses_10bit_pixel_format(self, profiles_dir):
        profile = load_profile("master-prores", profiles_dir=profiles_dir)
        assert "yuv422p10le" in profile.extra_args


class TestMasterDNxHRProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("master-dnxhr", profiles_dir=profiles_dir)

        assert profile.name == "master-dnxhr"
        assert profile.video_codec == "dnxhd"
        assert profile.audio_codec == "pcm_s24le"

    def test_uses_dnxhr_hqx_profile(self, profiles_dir):
        profile = load_profile("master-dnxhr", profiles_dir=profiles_dir)
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "dnxhr_hqx"


class TestListProfiles:
    def test_lists_all_new_profiles(self, profiles_dir):
        names = list_profiles(profiles_dir)

        assert "youtube-1080p" in names
        assert "youtube-4k" in names
        assert "vimeo-hq" in names
        assert "master-prores" in names
        assert "master-dnxhr" in names


# ---------------------------------------------------------------------------
# RenderProfile new fields tests
# ---------------------------------------------------------------------------

class TestRenderProfileNewFields:
    def test_fast_start_default_false(self):
        profile = RenderProfile(name="test")
        assert profile.fast_start is False

    def test_movflags_default_none(self):
        profile = RenderProfile(name="test")
        assert profile.movflags is None

    def test_fast_start_set_true(self):
        profile = RenderProfile(name="test", fast_start=True, movflags="+faststart")
        assert profile.fast_start is True
        assert profile.movflags == "+faststart"


# ---------------------------------------------------------------------------
# Codec availability check tests
# ---------------------------------------------------------------------------

class TestCheckCodecAvailable:
    @patch("subprocess.run")
    def test_available_codec_returns_true(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.LS h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
            " DEV.L. libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("libx264") is True

    @patch("subprocess.run")
    def test_unavailable_codec_returns_false(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.LS h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("libx265_nonexistent") is False

    @patch("subprocess.run")
    def test_ffmpeg_not_found_returns_false(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")

        assert check_codec_available("libx264") is False

    @patch("subprocess.run")
    def test_prores_codec_check(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.L. prores_ks            Apple ProRes (iCodec Pro)\n"
            " DEV.L. prores_aw            Apple ProRes\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("prores_ks") is True
        assert check_codec_available("prores_aw") is True
        assert check_codec_available("dnxhd") is False
