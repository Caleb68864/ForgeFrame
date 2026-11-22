"""Image file tools and the burned-in watermark on real files (prompt 39)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.pipelines.image_files import placement
from workshop_video_brain.edit_mcp.server.tools.image_files import (
    image_convert,
    image_overlay,
    image_resize,
    media_watermark,
)

from tests._testkit import (
    assert_registered,
    call_tool,
    make_test_clip,
    requires_ffmpeg_ffprobe,
)

pytestmark = requires_ffmpeg_ffprobe


def lavfi(out: Path, src: str, *extra: str) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, *extra, "-frames:v", "1", str(out)],
                   check=True, capture_output=True, timeout=60)
    return out


@pytest.fixture(scope="module")
def images(tmp_path_factory):
    d = tmp_path_factory.mktemp("img")
    return {
        "blue": lavfi(d / "blue.png", "color=c=blue:s=800x600"),
        "logo": lavfi(d / "logo.png", "color=c=white@1.0:s=200x100,format=rgba"),
        "wide": lavfi(d / "wide.png", "testsrc=s=1600x900"),
    }


def ok(result):
    assert result["status"] == "success", result
    return result["data"]


def size(path):
    asset = probe_media(Path(path))
    return asset.width, asset.height


def test_registered():
    assert_registered("image_resize", "image_convert", "image_overlay", "media_watermark")


def test_resize(images, tmp_path):
    data = ok(call_tool(image_resize, str(images["wide"]), width=800, output_dir=str(tmp_path)))
    assert size(data["output_path"]) == (800, 450) and data["output_path"].endswith("wide_800x450.png")
    cover = ok(call_tool(image_resize, str(images["wide"]), 400, 400, fit="cover", output_dir=str(tmp_path)))
    assert size(cover["output_path"]) == (400, 400)
    pad = ok(call_tool(image_resize, str(images["wide"]), 400, 400, fit="pad", output_path=str(tmp_path / "p.png")))
    assert size(pad["output_path"]) == (400, 400)
    PIL = pytest.importorskip("PIL.Image")
    with PIL.open(pad["output_path"]) as im:
        assert im.convert("RGB").getpixel((200, 0)) == (0, 0, 0)
    assert call_tool(image_resize, str(images["wide"]), 400, 400, fit="pad", pad_color="red:x")["error_type"] == "invalid_input"


def test_convert(images, tmp_path):
    webp = ok(call_tool(image_convert, str(images["wide"]), output_dir=str(tmp_path)))
    assert probe_media(Path(webp["output_path"])).video_codec == "webp"
    low = ok(call_tool(image_convert, str(images["wide"]), "jpg", 50, output_path=str(tmp_path / "q50.jpg")))
    high = ok(call_tool(image_convert, str(images["wide"]), "jpg", 95, output_path=str(tmp_path / "q95.jpg")))
    assert low["size_bytes"] < high["size_bytes"]
    white = ok(call_tool(image_convert, str(images["logo"]), "jpg", background="white",
                         output_path=str(tmp_path / "logo.jpg")))
    assert size(white["output_path"]) == (200, 100)


def test_overlay_half_opacity(images, tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    data = ok(call_tool(image_overlay, str(images["blue"]), str(images["logo"]), scale=0.15, opacity=0.5,
                        margin=0.05, output_dir=str(tmp_path)))
    with PIL.open(data["output_path"]) as im:
        rgb = im.convert("RGB")
        r, g, b = rgb.getpixel((700, 530))
        assert abs(r - 128) <= 6 and abs(g - 128) <= 6 and abs(b - 255) <= 6, (r, g, b)
        r, g, b = rgb.getpixel((10, 10))
        assert r <= 2 and g <= 2 and b >= 250, (r, g, b)


def test_watermark_on_video(images, tmp_path):
    from PIL import Image, ImageStat
    clip = make_test_clip(tmp_path / "blue.mp4", kind="color", color="blue", size=(640, 360), duration=5,
                          with_audio=True)
    data = ok(call_tool(media_watermark, str(clip), str(images["logo"]), start_seconds=1, end_seconds=3, opacity=1.0,
                        output_dir=str(tmp_path / "o")))
    out = Path(data["output_path"])
    assert out.name == "blue_wm.mp4"
    asset = probe_media(out)
    assert asset.duration_seconds == pytest.approx(5.0, abs=0.05) and asset.audio_codec
    x, y, w, h = placement(640, 360, 200, 100, "bottom_right", 0.15, 0.03)

    def mean_at(t):
        png = tmp_path / f"t{t}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(out), "-frames:v", "1", str(png)],
                       check=True, capture_output=True, timeout=60)
        with Image.open(png) as im:
            box = im.convert("L").crop((x + 4, y + 4, x + w - 4, y + h - 4))
            return ImageStat.Stat(box).mean[0]

    assert mean_at(2.0) > 200
    assert mean_at(4.0) < 100


def test_wrong_kinds(images, tmp_path):
    clip = make_test_clip(tmp_path / "c.mp4", duration=1)
    assert call_tool(media_watermark, str(images["blue"]), str(images["logo"]))["error_type"] == "invalid_input"
    assert call_tool(image_overlay, str(clip), str(images["logo"]))["error_type"] == "invalid_input"
    svg = tmp_path / "a.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert "PNG" in call_tool(image_resize, str(svg), 100)["message"]
    assert call_tool(image_overlay, str(images["blue"]), str(images["logo"]), position="middle")[
        "error_type"] == "invalid_input"
