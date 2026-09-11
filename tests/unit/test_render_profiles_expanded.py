"""Tests for expanded render profiles and codec availability check."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests._testkit import call_tool

from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    load_profile,
    list_profiles,
)
from workshop_video_brain.edit_mcp.adapters.render.executor import check_codec_available


# ---------------------------------------------------------------------------
# Shipped profiles, loaded the way users load them
# ---------------------------------------------------------------------------
# Every test below calls load_profile(name) / list_profiles() with NO
# profiles_dir, so it reads the YAML the repo actually ships through the
# default path the render tools use. These tests used to re-create all five
# profiles as inline dicts in tmp_path and pass that directory in -- so they
# stayed green while none of the five could be loaded by any tool, because
# the YAML sat in workshop-video-brain/templates/render and the loader reads
# <repo>/templates/render.

REPO_ROOT = Path(__file__).resolve().parents[2]

# The five profiles the README, the render_list_profiles docstring and the
# handbook promise.
DOCUMENTED_PROFILES = [
    "youtube-1080p",
    "youtube-4k",
    "vimeo-hq",
    "master-prores",
    "master-dnxhr",
]


class TestDocumentedProfilesAreReachable:
    @pytest.mark.parametrize("name", DOCUMENTED_PROFILES)
    def test_loads_from_the_default_path(self, name):
        profile = load_profile(name)
        assert profile.name == name

    def test_default_listing_includes_every_documented_profile(self):
        missing = sorted(set(DOCUMENTED_PROFILES) - set(list_profiles()))
        assert missing == []

    def test_every_shipped_render_yaml_is_visible_to_the_loader(self):
        """One render-profile directory: a YAML shipped anywhere else is dead.

        Scans ``templates/render`` at the repo root and one level down (where
        the plugin directory's copy used to live).
        """
        shipped = sorted(
            {p.stem for p in REPO_ROOT.glob("templates/render/*.yaml")}
            | {p.stem for p in REPO_ROOT.glob("*/templates/render/*.yaml")}
        )
        assert shipped, f"no render profiles found under {REPO_ROOT}"
        unreachable = sorted(set(shipped) - set(list_profiles()))
        assert unreachable == []

    def test_render_list_profiles_tool_reports_them_with_real_codecs(self):
        from workshop_video_brain.edit_mcp.server.tools.render import render_list_profiles

        result = call_tool(render_list_profiles)
        assert result["status"] == "success", result
        by_name = {p["name"]: p for p in result["data"]["profiles"]}
        for name in DOCUMENTED_PROFILES:
            assert name in by_name, sorted(by_name)
            # "unknown" is what the tool reports when a listed file fails to load.
            assert by_name[name]["codec"] != "unknown", by_name[name]


class TestYouTube1080pProfile:
    def test_loads_successfully(self):
        profile = load_profile("youtube-1080p")

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

    def test_has_h264_high_profile(self):
        profile = load_profile("youtube-1080p")
        assert "-profile:v" in profile.extra_args
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "high"


class TestYouTube4kProfile:
    def test_loads_successfully(self):
        profile = load_profile("youtube-4k")

        assert profile.name == "youtube-4k"
        assert profile.width == 3840
        assert profile.height == 2160
        assert profile.video_bitrate == "35M"

    def test_has_faststart(self):
        profile = load_profile("youtube-4k")
        assert "+faststart" in profile.extra_args


class TestVimeoHQProfile:
    def test_loads_successfully(self):
        profile = load_profile("vimeo-hq")

        assert profile.name == "vimeo-hq"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_bitrate == "320k"

    def test_uses_prores_profile_3(self):
        profile = load_profile("vimeo-hq")
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "3"


class TestMasterProResProfile:
    def test_loads_successfully(self):
        profile = load_profile("master-prores")

        assert profile.name == "master-prores"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_codec == "pcm_s24le"
        assert profile.video_bitrate == "0"
        assert profile.audio_bitrate == "0"

    def test_uses_10bit_pixel_format(self):
        profile = load_profile("master-prores")
        assert "yuv422p10le" in profile.extra_args


class TestMasterDNxHRProfile:
    def test_loads_successfully(self):
        profile = load_profile("master-dnxhr")

        assert profile.name == "master-dnxhr"
        assert profile.video_codec == "dnxhd"
        assert profile.audio_codec == "pcm_s24le"

    def test_uses_dnxhr_hqx_profile(self):
        profile = load_profile("master-dnxhr")
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "dnxhr_hqx"


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
