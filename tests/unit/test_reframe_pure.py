"""Reframe maths (prompt 33; no ffmpeg)."""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.reframe import (
    best_focus_x,
    column_energy,
    crop_box,
    filter_for,
    target_size,
)


def test_crop_box_landscape_to_vertical():
    assert crop_box(1920, 1080, 9, 16) == (656, 0, 606, 1080)
    assert crop_box(1920, 1080, 9, 16, focus_x=0)[0] == 0
    assert crop_box(1920, 1080, 9, 16, focus_x=1)[0] == 1314
    assert all(v % 2 == 0 for v in crop_box(1918, 1078, 4, 5, 0.37, 0.61))


def test_crop_box_square_from_portrait_crops_height():
    x, y, w, h = crop_box(1080, 1920, 1, 1)
    assert (w, h, x) == (1080, 1080, 0) and y == 420


def test_target_size():
    assert target_size("9:16") == (1080, 1920)
    assert target_size("9:16", height=320) == (180, 320)


def test_best_focus():
    assert best_focus_x([1.0] * 160, 54) == 0.5
    spike = [0.0] * 160
    spike[140] = 100.0
    assert best_focus_x(spike, 54) > 0.7


def test_column_energy_finds_motion():
    w, h = 8, 2
    a = bytes([0] * 16)
    b = bytearray(16)
    b[6] = b[14] = 255  # bright pixel appears in column 6
    energy = column_energy([a, bytes(b)], w, h)
    assert max(range(w), key=lambda i: energy[i]) == 6


def test_filters():
    assert filter_for("crop", 1920, 1080, 1080, 1920, 0.5) == "crop=606:1080:656:0,scale=1080:1920,setsar=1"
    assert "force_original_aspect_ratio=decrease,pad=1080:1920" in filter_for("pad", 1920, 1080, 1080, 1920)
    blur = filter_for("blur", 1920, 1080, 1080, 1080)
    assert "boxblur=20:5" in blur and "overlay=(W-w)/2:(H-h)/2" in blur
