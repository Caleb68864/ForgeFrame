"""Unit tests for the proxy adapter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models import MediaAsset
from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
    ProxyPolicy,
    generate_proxy,
    needs_proxy,
    proxy_path_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asset(
    path: str = "/media/raw/clip.mp4",
    media_type: str = "video",
    video_codec: str = "h264",
    width: int = 1280,
    height: int = 720,
    bitrate: int = 10_000_000,
) -> MediaAsset:
    return MediaAsset(
        path=path,
        media_type=media_type,
        video_codec=video_codec,
        width=width,
        height=height,
        bitrate=bitrate,
    )


# ---------------------------------------------------------------------------
# Tests: needs_proxy
# ---------------------------------------------------------------------------

class TestNeedsProxy:
    def test_low_res_low_bitrate_no_proxy(self):
        asset = _make_asset(width=1280, height=720, bitrate=10_000_000)
        assert needs_proxy(asset) is False

    def test_1080p_at_threshold_no_proxy(self):
        # Exactly at the 1920x1080 threshold should NOT trigger
        asset = _make_asset(width=1920, height=1080)
        assert needs_proxy(asset) is False

    def test_resolution_exceeds_width(self):
        asset = _make_asset(width=2560, height=1080)
        assert needs_proxy(asset) is True

    def test_resolution_exceeds_height(self):
        asset = _make_asset(width=1920, height=1440)
        assert needs_proxy(asset) is True

    def test_4k_needs_proxy(self):
        asset = _make_asset(width=3840, height=2160)
        assert needs_proxy(asset) is True

    def test_hevc_codec_needs_proxy(self):
        asset = _make_asset(video_codec="hevc", width=1280, height=720)
        assert needs_proxy(asset) is True

    def test_h265_codec_needs_proxy(self):
        asset = _make_asset(video_codec="h265", width=1280, height=720)
        assert needs_proxy(asset) is True

    def test_prores_codec_needs_proxy(self):
        asset = _make_asset(video_codec="prores", width=1280, height=720)
        assert needs_proxy(asset) is True

    def test_h264_codec_no_proxy_by_codec(self):
        asset = _make_asset(video_codec="h264", width=1280, height=720, bitrate=5_000_000)
        assert needs_proxy(asset) is False

    def test_high_bitrate_needs_proxy(self):
        # 60 Mbps > default 50 Mbps
        asset = _make_asset(bitrate=60_000_000, width=1280, height=720)
        assert needs_proxy(asset) is True

    def test_bitrate_at_threshold_no_proxy(self):
        # Exactly 50 Mbps does not trigger
        asset = _make_asset(bitrate=50_000_000, width=1280, height=720)
        assert needs_proxy(asset) is False

    def test_audio_asset_never_needs_proxy(self):
        asset = _make_asset(media_type="audio", width=0, height=0)
        assert needs_proxy(asset) is False

    def test_custom_policy_max_width(self):
        policy = ProxyPolicy(max_width=1280, max_height=720)
        asset = _make_asset(width=1920, height=1080)
        # 1920 > 1280 should trigger with tight policy
        assert needs_proxy(asset, policy) is True

    def test_custom_policy_codec(self):
        policy = ProxyPolicy(heavy_codecs={"vp9"})
        asset = _make_asset(video_codec="vp9", width=640, height=480)
        assert needs_proxy(asset, policy) is True

    def test_custom_policy_bitrate(self):
        policy = ProxyPolicy(max_bitrate_mbps=5.0)
        asset = _make_asset(bitrate=10_000_000)  # 10 Mbps > 5 Mbps
        assert needs_proxy(asset, policy) is True

    def test_none_policy_uses_defaults(self):
        asset = _make_asset(width=3840, height=2160)
        assert needs_proxy(asset, None) is True


# ---------------------------------------------------------------------------
# Tests: proxy_path_for
# ---------------------------------------------------------------------------

class TestProxyPathFor:
    def test_deterministic_mapping(self, tmp_path):
        asset = _make_asset(path="/media/raw/my_clip.mp4")
        p1 = proxy_path_for(asset, tmp_path)
        p2 = proxy_path_for(asset, tmp_path)
        assert p1 == p2

    def test_proxy_stem_suffix(self, tmp_path):
        asset = _make_asset(path="/media/raw/my_clip.mp4")
        p = proxy_path_for(asset, tmp_path)
        assert p.name == "my_clip_proxy.mp4"
        assert p.parent == tmp_path

    def test_different_assets_different_paths(self, tmp_path):
        a1 = _make_asset(path="/media/raw/clip1.mp4")
        a2 = _make_asset(path="/media/raw/clip2.mp4")
        assert proxy_path_for(a1, tmp_path) != proxy_path_for(a2, tmp_path)


# ---------------------------------------------------------------------------
# Tests: generate_proxy
# ---------------------------------------------------------------------------

class TestGenerateProxy:
    def test_calls_ffmpeg(self, tmp_path):
        source = tmp_path / "clip.mp4"
        source.write_bytes(b"\x00")
        asset = _make_asset(path=str(source))

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock()
            out = generate_proxy(asset, tmp_path / "proxies")

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-crf" in cmd

    def test_output_path_returned(self, tmp_path):
        source = tmp_path / "clip.mp4"
        source.write_bytes(b"\x00")
        asset = _make_asset(path=str(source))

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock()
            out = generate_proxy(asset, tmp_path / "proxies")

        assert out.name == "clip_proxy.mp4"

    def test_skips_if_proxy_newer_than_source(self, tmp_path):
        import time

        source = tmp_path / "clip.mp4"
        source.write_bytes(b"\x00")

        proxy_dir = tmp_path / "proxies"
        proxy_dir.mkdir()
        asset = _make_asset(path=str(source))
        proxy = proxy_path_for(asset, proxy_dir)

        # Write proxy and make it newer
        time.sleep(0.05)
        proxy.write_bytes(b"\x00")

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy.subprocess.run"
        ) as mock_run:
            out = generate_proxy(asset, proxy_dir)

        mock_run.assert_not_called()
        assert out == proxy

    def test_regenerates_stale_proxy(self, tmp_path):
        import time

        proxy_dir = tmp_path / "proxies"
        proxy_dir.mkdir()

        # Create proxy first, then create source (source is newer)
        asset_path = tmp_path / "clip.mp4"
        proxy = proxy_dir / "clip_proxy.mp4"
        proxy.write_bytes(b"\x00")
        time.sleep(0.05)
        asset_path.write_bytes(b"\x00")  # source is newer than proxy

        asset = _make_asset(path=str(asset_path))

        with patch(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock()
            generate_proxy(asset, proxy_dir)

        mock_run.assert_called_once()
