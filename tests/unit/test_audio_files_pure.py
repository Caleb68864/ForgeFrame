"""Music-bed graph and fade filter (prompt 34; no ffmpeg)."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.audio_files import build_mix_graph, fade_filter


def test_mix_graph_ducking_and_options():
    ducked = build_mix_graph(-18, True, "strong", False, 0.0, 1.0, 2.0, 10.0)
    assert "sidechaincompress=threshold=0.02:ratio=20:attack=20:release=250" in ducked
    assert "normalize=0" in ducked and "aloop" not in ducked
    assert "afade=t=out:st=8.000:d=2.000" in ducked
    plain = build_mix_graph(-18, False, "medium", True, 1.5, 0, 0, 10.0)
    assert "asplit" not in plain and "sidechaincompress" not in plain and "afade" not in plain
    assert plain.startswith("[1:a]aloop=loop=-1:size=2147483647,atrim=start=1.500")
    with pytest.raises(ValueError):
        build_mix_graph(-18, True, "huge", False, 0, 0, 0, 1)


def test_fade_filter():
    assert fade_filter(5.0, 1.0, 1.0) == "afade=t=in:st=0:d=1.000:curve=tri,afade=t=out:st=4.000:d=1.000:curve=tri"
    for args in ((5.0, 0, 0), (2.0, 1.5, 1.0), (5.0, 1.0, 0, "wobble")):
        with pytest.raises(ValueError):
            fade_filter(*args)
