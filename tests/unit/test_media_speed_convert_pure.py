"""Pure parts of media_speed / media_rotate_flip / media_convert (prompt 31; no ffmpeg)."""
from __future__ import annotations

import math

import pytest

from workshop_video_brain.edit_mcp.pipelines.media_convert import pick_preset
from workshop_video_brain.edit_mcp.pipelines.media_edit import atempo_chain, rotate_flip_filter


@pytest.mark.parametrize("factor", [0.25, 0.5, 0.8, 1.5, 2.0, 3.0, 4.0])
def test_atempo_chain(factor):
    stages = [float(part.split("=")[1]) for part in atempo_chain(factor).split(",")]
    assert all(0.5 <= s <= 2.0 for s in stages)
    assert math.prod(stages) == pytest.approx(factor, abs=1e-6)


def test_atempo_range():
    with pytest.raises(ValueError):
        atempo_chain(5.0)


@pytest.mark.parametrize("rotate, flip, chain", [
    (90, "", "transpose=1"), (180, "", "hflip,vflip"), (270, "", "transpose=2"),
    (0, "horizontal", "hflip"), (0, "vertical", "vflip"), (0, "both", "hflip,vflip"),
    (90, "horizontal", "transpose=1,hflip"),
])
def test_rotate_flip_filter(rotate, flip, chain):
    assert rotate_flip_filter(rotate, flip) == chain


@pytest.mark.parametrize("rotate, flip", [(0, ""), (45, ""), (0, "sideways")])
def test_rotate_flip_refusals(rotate, flip):
    with pytest.raises(ValueError):
        rotate_flip_filter(rotate, flip)


def test_presets():
    assert pick_preset(".mp4") == "h264" and pick_preset(".webm") == "vp9"
    assert pick_preset(".mov", "prores") == "prores" and pick_preset(".mkv", "hevc") == "hevc"
    for ext, preset in ((".xyz", ""), (".mp4", "prores"), (".webm", "hevc"), (".mp4", "magic")):
        with pytest.raises(ValueError):
            pick_preset(ext, preset)
