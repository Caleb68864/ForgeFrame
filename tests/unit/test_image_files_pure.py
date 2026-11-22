"""Image file builders (prompt 39; no ffmpeg)."""
from __future__ import annotations

import pytest
from workshop_video_brain.edit_mcp.pipelines.image_files import (
    format_args,
    jpeg_qscale,
    overlay_graph,
    placement,
    resize_filter,
)
from workshop_video_brain.edit_mcp.pipelines.image_overlay import position_rect


def test_resize_filter_modes():
    assert resize_filter(1600, 900, 400, 400, "contain") == "scale=400:400:force_original_aspect_ratio=decrease"
    assert resize_filter(1600, 900, 400, 400, "cover") == (
        "scale=400:400:force_original_aspect_ratio=increase,crop=400:400")
    assert resize_filter(1600, 900, 400, 400, "stretch") == "scale=400:400"
    assert resize_filter(1600, 900, 400, 400, "pad", "white").endswith(",pad=400:400:(ow-iw)/2:(oh-ih)/2:color=white")
    assert resize_filter(1600, 900, 800, 0) == "scale=800:-1"
    assert resize_filter(1600, 900, 0, 300) == "scale=-1:300"


@pytest.mark.parametrize("args", [(0, 0, "contain"), (400, 400, "squash"), (20000, 10, "contain"),
                                  (400, 400, "pad", "red;evil")])
def test_resize_filter_rejects(args):
    with pytest.raises(ValueError):
        resize_filter(100, 100, *args)


def test_quality_map():
    assert jpeg_qscale(100) == 2 and jpeg_qscale(1) == 31
    values = [jpeg_qscale(q) for q in range(1, 101)]
    assert values == sorted(values, reverse=True)
    assert format_args(".jpg", 50) == ["-q:v", str(jpeg_qscale(50))]
    assert format_args(".webp", 70) == ["-c:v", "libwebp", "-quality", "70"]
    with pytest.raises(ValueError):
        format_args(".svg")
    with pytest.raises(ValueError):
        jpeg_qscale(0)


def test_placement_matches_the_timeline_tools():
    assert placement(800, 600, 200, 100, "bottom_right", 0.15, 0.05) == (640, 510, 120, 60)
    assert placement(800, 600, 200, 100, "bottom_right", 0.15, 0.05) == position_rect(
        "bottom_right", 800, 600, scale=0.15, margin=0.05, aspect=2.0)
    assert placement(800, 600, 200, 100, "custom", 0.25, x=10, y=20) == (10, 20, 200, 100)
    assert placement(800, 600, 200, 100, "full") == (0, 0, 800, 600)
    with pytest.raises(ValueError, match="custom"):
        placement(800, 600, 200, 100, "middle")


def test_overlay_graph():
    graph = overlay_graph(640, 510, 120, 60, 0.5, enable=(1, 3))
    assert graph == ("[1:v]format=rgba,scale=120:60,colorchannelmixer=aa=0.5000[wm];"
                     "[0:v][wm]overlay=640:510:format=auto:enable='between(t,1,3)'")
    assert "colorchannelmixer" not in overlay_graph(0, 0, 10, 10, 1.0)
    with pytest.raises(ValueError):
        overlay_graph(0, 0, 10, 10, 1.5)
