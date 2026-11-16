"""Real-ffmpeg proof for the reaction-GIF render, contact sheet, cuts and check strip.

Synthetic clip: 2 s of ``testsrc`` then a hard cut to 2 s of solid green, with
a sine tone throughout. No network.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.pipelines import reaction_gif as rg

pytestmark = requires_ffmpeg_ffprobe

CUT = 2.0


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("rg") / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25:duration={CUT}",
            "-f", "lavfi", "-i", f"color=c=0x00ff00:size=640x360:rate=25:duration={CUT}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={CUT * 2}",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True, capture_output=True, timeout=120,
    )
    return out


def _frames(gif: Path):
    from PIL import Image, ImageSequence

    with Image.open(gif) as im:
        return [f.convert("RGB").copy() for f in ImageSequence.Iterator(im)]


def _pixels(img) -> list[tuple[int, int, int]]:
    raw = img.convert("RGB").tobytes()
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


def _green_fraction(img) -> float:
    w, h = img.size
    top = img.crop((0, 0, w, int(h * 0.6)))  # above the caption
    px = _pixels(top)
    return sum(1 for r, g, b in px if g > 200 and r < 60 and b < 60) / len(px)


def test_scene_cut_detected(clip):
    cuts = rg.detect_scene_cuts(clip)
    assert any(abs(t - CUT) < 0.05 for t in cuts), cuts


def test_render_ends_before_cut(clip, tmp_path):
    end = rg.end_before_cut(CUT)
    result = rg.render_gif(clip, 0.5, end, "I'VE GOT IT!", output=tmp_path / "out.gif")
    gif = Path(result["path"])
    assert gif.exists() and gif.stat().st_size > 0
    assert result["width"] == 480
    assert result["fps"] == pytest.approx(15, abs=0.5)
    assert result["duration"] == pytest.approx(end - 0.5, abs=0.1)
    assert result["size_bytes"] == gif.stat().st_size

    frames = _frames(gif)
    assert frames[0].size[0] == 480
    assert len(frames) == pytest.approx((end - 0.5) * 15, abs=2)
    # No frame from the second (solid green) shot got in.
    assert max(_green_fraction(f) for f in frames) < 0.5

    strip = Path(result["check_strip"])
    assert strip.exists() and strip.stat().st_size > 0


def test_end_after_cut_does_include_second_shot(clip, tmp_path):
    """Control: the green-detector works, so the test above is meaningful."""
    result = rg.render_gif(clip, 1.5, 3.0, None, output=tmp_path / "ctl.gif")
    frames = _frames(Path(result["path"]))
    assert max(_green_fraction(f) for f in frames) > 0.9


def test_caption_is_applied(clip, tmp_path):
    with_cap = rg.render_gif(clip, 0.5, 1.5, "I'VE GOT IT!", output=tmp_path / "a.gif")
    no_cap = rg.render_gif(clip, 0.5, 1.5, None, output=tmp_path / "b.gif")
    a = _frames(Path(with_cap["path"]))[5]
    b = _frames(Path(no_cap["path"]))[5]
    w, h = a.size
    m = rg.caption_metrics(w)
    band = (0, h - m.fontsize - m.margin - m.borderw, w, h)
    top = (0, 0, w, int(h * 0.4))

    def diff(box):
        pa, pb = _pixels(a.crop(box)), _pixels(b.crop(box))
        return sum(1 for x, y in zip(pa, pb) if sum(abs(i - j) for i, j in zip(x, y)) > 120) / len(pa)

    assert diff(band) > 0.05  # caption pixels changed the bottom band
    assert diff(top) < 0.02  # and nothing else


def test_contact_sheet_and_waveform(clip, tmp_path):
    sheet = rg.make_contact_sheet(clip, tmp_path / "sheet.png")
    wave = rg.make_waveform(clip, 0.0, tmp_path / "wave.png", duration=3.0)
    from PIL import Image

    with Image.open(sheet) as im:
        assert im.size == (240 * 6, 135 * 10)
    with Image.open(wave) as im:
        assert im.size == (1200, 200)


def test_default_output_goes_to_gallery(clip, tmp_path, monkeypatch):
    monkeypatch.setenv("WVB_GIF_GALLERY", str(tmp_path / "gallery"))
    result = rg.render_gif(clip, 0.5, 1.0, "Hi there")
    assert Path(result["path"]) == tmp_path / "gallery" / "hi-there.gif"
