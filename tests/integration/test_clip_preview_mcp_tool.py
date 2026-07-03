"""Integration tests for the ``clips_preview_gif`` MCP bundle tool.

Generates a real preview with FFmpeg and asserts dimensions, frame count and
size via ffprobe.  FFmpeg-gated (skipped when ffmpeg / ffprobe are
unavailable).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

ffmpeg_available = (
    shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
)
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg/ffprobe not available on PATH"
)

from workshop_video_brain.edit_mcp.server.bundles import clip_preview as bundle


def _callable(obj):
    return getattr(obj, "fn", obj)


clips_preview_gif = _callable(bundle.clips_preview_gif)


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "reports").mkdir(parents=True)
    (ws / "media" / "raw").mkdir(parents=True)
    return ws


def _make_clip(path: Path, duration: float = 5.0) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=size=640x480:rate=25:duration={duration}",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True,
    )


class TestGifPreview:
    def test_generates_gif_with_expected_geometry(self, tmp_path):
        ws = _make_workspace(tmp_path)
        clip = tmp_path / "shot.mp4"
        _make_clip(clip)

        res = clips_preview_gif(
            workspace_path=str(ws), source=str(clip),
            seconds=3, fps=8, width=320, format="gif",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["format"] == "gif"
        assert data["width"] == 320
        assert data["frame_count"] == 24  # 3s * 8fps
        assert data["expected_frame_count"] == 24
        assert data["size_bytes"] > 0

        out = Path(data["output"])
        assert out.exists()
        assert out.suffix == ".gif"
        # written under reports/previews, never media/raw
        assert out.parent.name == "previews"
        assert out.parent.parent.name == "reports"
        assert list((ws / "media" / "raw").iterdir()) == []
        # the intermediate palette is cleaned up
        assert not (out.parent / f"{clip.stem}_palette.png").exists()

    def test_source_relative_to_workspace(self, tmp_path):
        ws = _make_workspace(tmp_path)
        (ws / "media" / "processed").mkdir(parents=True)
        clip = ws / "media" / "processed" / "rel.mp4"
        _make_clip(clip)
        res = clips_preview_gif(
            workspace_path=str(ws),
            source="media/processed/rel.mp4",
            seconds=2, fps=8, width=160,
        )
        assert res["status"] == "success", res
        assert res["data"]["width"] == 160
        assert res["data"]["frame_count"] == 16


class TestMp4Preview:
    def test_generates_mp4(self, tmp_path):
        ws = _make_workspace(tmp_path)
        clip = tmp_path / "shot.mp4"
        _make_clip(clip)
        res = clips_preview_gif(
            workspace_path=str(ws), source=str(clip),
            seconds=2, fps=10, width=240, format="mp4",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["format"] == "mp4"
        assert data["width"] == 240
        assert data["frame_count"] == 20  # 2s * 10fps
        assert Path(data["output"]).suffix == ".mp4"


class TestErrors:
    def test_bad_format(self, tmp_path):
        ws = _make_workspace(tmp_path)
        clip = tmp_path / "s.mp4"
        _make_clip(clip, duration=1.0)
        res = clips_preview_gif(
            workspace_path=str(ws), source=str(clip), format="webm",
        )
        assert res["status"] == "error"
        assert "format" in res["message"].lower()

    def test_missing_source(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = clips_preview_gif(
            workspace_path=str(ws), source=str(tmp_path / "nope.mp4"),
        )
        assert res["status"] == "error"

    def test_nonpositive_seconds(self, tmp_path):
        ws = _make_workspace(tmp_path)
        clip = tmp_path / "s.mp4"
        _make_clip(clip, duration=1.0)
        res = clips_preview_gif(
            workspace_path=str(ws), source=str(clip), seconds=0,
        )
        assert res["status"] == "error"


class TestRegistration:
    def test_registered_via_list_tools(self):
        import asyncio
        import inspect
        from workshop_video_brain import server

        getter = getattr(server.mcp, "list_tools", None) or server.mcp.get_tools
        result = getter()
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        names = (
            list(result.keys()) if isinstance(result, dict)
            else [t.name for t in result]
        )
        assert "clips_preview_gif" in names
