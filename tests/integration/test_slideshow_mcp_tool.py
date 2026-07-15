"""Integration tests for the ``media_slideshow`` MCP bundle tool.

Empirically generates test PNGs with FFmpeg, builds a slideshow, and ffprobes
the result's duration and resolution.  FFmpeg-gated (skipped when ffmpeg /
ffprobe are unavailable).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

ffmpeg_available = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg/ffprobe not available on PATH"
)

from workshop_video_brain.edit_mcp.server.bundles import slideshow as bundle
from workshop_video_brain.edit_mcp.server import tools as tools_mod


def _callable(obj):
    """Unwrap a possibly-``FunctionTool``-wrapped MCP tool to its function."""
    return getattr(obj, "fn", obj)


media_slideshow = _callable(bundle.media_slideshow)
workspace_create = _callable(tools_mod.workspace_create)


def _make_workspace(tmp_path: Path) -> Path:
    media_root = tmp_path / "media_src"
    media_root.mkdir(parents=True, exist_ok=True)
    res = workspace_create(title="Slideshow Test", media_root=str(media_root))
    assert res["status"] == "success", res
    return Path(res["data"]["workspace_root"])


def _gen_pngs(folder: Path, count: int = 5, mixed: bool = False) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        ext = "jpg" if (mixed and i % 2 == 0) else "png"
        name = folder / f"frame{i:03d}.{ext}"
        color = f"0x{i*30 % 256:02x}20{i*40 % 256:02x}"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"color=c={color}:s={300 + i * 20}x{200 + i * 15}:d=1",
                "-frames:v", "1", str(name),
            ],
            capture_output=True, check=True,
        )


def _probe(path: Path) -> tuple[float, int, int]:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration:stream=width,height",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    vals = out.stdout.split()
    width, height, duration = int(vals[0]), int(vals[1]), float(vals[2])
    return duration, width, height


class TestMediaSlideshow:
    def test_builds_uniform_sequence_pattern_backend(self, tmp_path):
        ws = _make_workspace(tmp_path)
        imgs = tmp_path / "photos"
        _gen_pngs(imgs, count=5)

        res = media_slideshow(
            workspace_path=str(ws),
            image_folder=str(imgs),
            duration_per_image_seconds=0.5,
            resolution="1280x720",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["image_count"] == 5
        assert data["backend"] == "pattern"
        assert data["resolution"] == "1280x720"

        out = Path(data["output"])
        assert out.exists()
        assert out.parent.name == "processed"  # never media/raw

        duration, width, height = _probe(out)
        assert (width, height) == (1280, 720)
        # 5 images x 0.5s = 2.5s
        assert duration == pytest.approx(2.5, abs=0.2)
        assert data["expected_duration_seconds"] == pytest.approx(2.5, abs=0.01)

    def test_mixed_extensions_filtergraph_backend(self, tmp_path):
        ws = _make_workspace(tmp_path)
        imgs = tmp_path / "mixed"
        _gen_pngs(imgs, count=4, mixed=True)

        res = media_slideshow(
            workspace_path=str(ws),
            image_folder=str(imgs),
            duration_per_image_seconds=0.5,
            resolution="640x480",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["backend"] == "filtergraph"
        assert data["image_count"] == 4
        duration, width, height = _probe(Path(data["output"]))
        assert (width, height) == (640, 480)
        assert duration == pytest.approx(2.0, abs=0.3)

    def test_crossfade_shortens_total(self, tmp_path):
        ws = _make_workspace(tmp_path)
        imgs = tmp_path / "xf"
        _gen_pngs(imgs, count=4)

        res = media_slideshow(
            workspace_path=str(ws),
            image_folder=str(imgs),
            duration_per_image_seconds=1.0,
            crossfade_frames=10,  # 0.4s at 25fps
            resolution="640x480",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["backend"] == "filtergraph"
        # 4*1.0 - 3*0.4 = 2.8
        assert data["expected_duration_seconds"] == pytest.approx(2.8, abs=0.01)
        duration, _, _ = _probe(Path(data["output"]))
        assert duration == pytest.approx(2.8, abs=0.3)

    def test_kenburns_builds(self, tmp_path):
        ws = _make_workspace(tmp_path)
        imgs = tmp_path / "kb"
        _gen_pngs(imgs, count=3)

        res = media_slideshow(
            workspace_path=str(ws),
            image_folder=str(imgs),
            duration_per_image_seconds=0.5,
            kenburns=True,
            resolution="640x480",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["kenburns"] is True
        _, width, height = _probe(Path(data["output"]))
        assert (width, height) == (640, 480)

    def test_empty_folder_errors(self, tmp_path):
        ws = _make_workspace(tmp_path)
        empty = tmp_path / "empty"
        empty.mkdir()
        res = media_slideshow(workspace_path=str(ws), image_folder=str(empty))
        assert res["status"] == "error"
        assert "No images" in res["message"]


class TestRegistration:
    def test_media_slideshow_registered_via_list_tools(self):
        import asyncio
        import inspect

        from workshop_video_brain import server

        # fastmcp exposes tool enumeration as ``list_tools`` (newer) or
        # ``get_tools`` (older); support both, sync or async.
        getter = getattr(server.mcp, "list_tools", None) or server.mcp.get_tools
        result = getter()
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        names = list(result.keys()) if isinstance(result, dict) else [t.name for t in result]
        assert "media_slideshow" in names
