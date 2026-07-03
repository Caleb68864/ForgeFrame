"""Unit tests for the review-loop pipeline pure helpers (gap 5a / 5b).

Covers interval math, marker parsing, thumbnail-style handling and the output
directory shape -- none of which need ffmpeg or melt.
"""
from __future__ import annotations

import json

import pytest

from workshop_video_brain.edit_mcp.pipelines import review_loop as rl


# --- interval math ---------------------------------------------------------

def test_frame_timestamps_basic():
    assert rl.frame_timestamps(10.0, 2.0) == [0.0, 2.0, 4.0, 6.0, 8.0]


def test_frame_timestamps_excludes_duration_endpoint():
    # A frame exactly at duration is past the last frame -- must not appear.
    ts = rl.frame_timestamps(8.0, 2.0)
    assert ts == [0.0, 2.0, 4.0, 6.0]
    assert 8.0 not in ts


def test_frame_timestamps_zero_duration_empty():
    assert rl.frame_timestamps(0.0, 2.0) == []
    assert rl.frame_timestamps(-5.0, 2.0) == []


def test_frame_timestamps_bad_interval_raises():
    with pytest.raises(ValueError):
        rl.frame_timestamps(10.0, 0.0)
    with pytest.raises(ValueError):
        rl.frame_timestamps(10.0, -1.0)


def test_frame_timestamps_fractional_interval():
    ts = rl.frame_timestamps(2.0, 0.5)
    assert ts == [0.0, 0.5, 1.0, 1.5]


# --- marker parsing --------------------------------------------------------

def test_marker_timestamps_reads_and_sorts_unique(tmp_path):
    mdir = tmp_path / "markers"
    mdir.mkdir()
    (mdir / "a_markers.json").write_text(json.dumps([
        {"category": "chapter_candidate", "start_seconds": 5.0},
        {"category": "chapter_candidate", "start_seconds": 1.0},
    ]))
    (mdir / "b_markers.json").write_text(json.dumps([
        {"category": "highlight", "start_seconds": 5.0},  # dup
        {"category": "highlight", "start_seconds": 3.5},
    ]))
    assert rl.marker_timestamps(tmp_path) == [1.0, 3.5, 5.0]


def test_marker_timestamps_no_dir(tmp_path):
    assert rl.marker_timestamps(tmp_path) == []


def test_marker_timestamps_skips_bad_files(tmp_path):
    mdir = tmp_path / "markers"
    mdir.mkdir()
    (mdir / "broken.json").write_text("{not json")
    (mdir / "obj.json").write_text(json.dumps({"start_seconds": 9.0}))  # not a list
    (mdir / "good.json").write_text(json.dumps([{"start_seconds": 2.0}]))
    assert rl.marker_timestamps(tmp_path) == [2.0]


# --- style handling --------------------------------------------------------

def test_load_thumbnail_style_returns_vocab():
    style = rl.load_thumbnail_style("thumbnail")
    assert style["font_family"] == "DejaVu Sans"
    assert style["outline_width"] == 8
    assert "title_font_scale" in style
    # Only whitelisted drawing fields survive.
    assert set(style).issubset(rl._THUMBNAIL_STYLE_FIELDS)


def test_load_thumbnail_style_unknown_raises():
    with pytest.raises(ValueError):
        rl.load_thumbnail_style("does-not-exist")


def test_load_thumbnail_style_reuses_title_templates():
    # lower-third is a shared title template; the loader should read it too.
    style = rl.load_thumbnail_style("lower-third")
    assert style["anchor"] == "lower-third"


# --- output dir shape ------------------------------------------------------

def test_review_output_dir_shape(tmp_path):
    out = rl.review_output_dir(tmp_path, timestamp="20260101-000000")
    assert out == tmp_path / "reports" / "review" / "20260101-000000"


def test_rgba_parsing():
    assert rl._rgba("#FFFFFF") == (255, 255, 255, 255)
    assert rl._rgba("#000000B4") == (0, 0, 0, 180)
    assert rl._rgba("255,215,0") == (255, 215, 0, 255)
