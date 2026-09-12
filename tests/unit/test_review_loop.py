"""Unit tests for the review-loop pipeline pure helpers (gap 5a / 5b).

Covers interval math, marker parsing, thumbnail-style handling, the output
directory shape and the pre-melt media precondition on project thumbnails --
none of which need ffmpeg or melt (the melt/ffmpeg calls are faked).
"""
from __future__ import annotations

import json
from pathlib import Path

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


# --- thumbnails off a project: the same missing-media precondition ----------

def _project_xml(path, producers, *, root=None):
    """Write a minimal MLT XML with (mlt_service, resource) producers."""
    root_attr = f' root="{root}"' if root else ""
    body = "\n".join(
        f'  <producer id="p{i}">\n'
        f'    <property name="mlt_service">{service}</property>\n'
        f'    <property name="resource">{resource}</property>\n'
        f"  </producer>"
        for i, (service, resource) in enumerate(producers)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0"?>\n<mlt version="7"{root_attr}>\n{body}\n</mlt>\n',
        encoding="utf-8",
    )
    return path


def _fake_melt(monkeypatch):
    """Stand in for melt: write the PNG frames it was asked for, exit 0.

    This is melt's real behaviour on a project whose media is gone -- it warns,
    renders the clip as blank frames, and still exits 0 -- so a test using it
    reproduces the defect without needing melt installed.
    """
    import subprocess as sp

    from PIL import Image

    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd)
        target = next((c for c in cmd if str(c).startswith("avformat:")), "")
        pattern = Path(str(target)[len("avformat:"):])
        pattern.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (0, 0, 0)).save(
            pattern.parent / "f_00000.png", "PNG"
        )
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(rl.subprocess, "run", _run)
    return calls


class TestThumbnailFromProjectMediaPrecondition:
    """``thumbnail_generate`` on a ``.kdenlive`` source goes through melt.

    melt renders footage it cannot open as blank frames and exits 0, so a
    project whose media had been deleted produced a **black thumbnail** and
    reported success. A thumbnail is a publish artifact; a blank one that says
    "success" is the same false result the render path was fixed for, so the
    same precondition applies -- reached through the same implementation, not a
    second copy of it.
    """

    def test_reject_project_with_missing_media_is_not_a_blank_thumbnail(
        self, tmp_path, monkeypatch
    ):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project_xml(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        calls = _fake_melt(monkeypatch)

        result = rl.thumbnail_generate(tmp_path, str(proj), 1.0, text="Hi")

        assert result["success"] is False, result
        assert result["error_type"] == "missing_file", result
        assert str(gone) in result["error"], result
        assert calls == [], "melt must not be run for a project that cannot render"

    def test_accept_project_with_all_media_present_still_makes_a_thumbnail(
        self, tmp_path, monkeypatch
    ):
        """The control: the precondition must not refuse every project."""
        here = tmp_path / "media" / "shot.mp4"
        here.parent.mkdir(parents=True, exist_ok=True)
        here.write_bytes(b"\x00\x11\x22\x33" * 64)
        proj = _project_xml(tmp_path / "p.kdenlive", [("avformat", str(here))])
        calls = _fake_melt(monkeypatch)

        result = rl.thumbnail_generate(tmp_path, str(proj), 1.0, text="Hi")

        assert result["success"] is True, result
        assert Path(result["output_path"]).exists()
        assert len(calls) == 1

    def test_accept_colour_and_title_only_project_still_makes_a_thumbnail(
        self, tmp_path, monkeypatch
    ):
        """A title card over a colour background references no file at all."""
        proj = _project_xml(
            tmp_path / "p.kdenlive",
            [("color", "black"), ("kdenlivetitle", ""), ("qtext", "Chapter 1")],
        )
        calls = _fake_melt(monkeypatch)

        result = rl.thumbnail_generate(tmp_path, str(proj), 0.0, text="Chapter 1")

        assert result["success"] is True, result
        assert len(calls) == 1

    def test_a_plain_media_source_is_unaffected(self, tmp_path, monkeypatch):
        """The ffmpeg path does not go near the project check."""
        import subprocess as sp

        from PIL import Image

        src = tmp_path / "clip.mp4"
        src.write_bytes(b"\x00\x11\x22\x33" * 64)

        def _run(cmd, **kwargs):
            Image.new("RGB", (64, 36), (10, 20, 30)).save(cmd[-1], "PNG")
            return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(rl.subprocess, "run", _run)
        result = rl.thumbnail_generate(tmp_path, str(src), 0.5, text="Hi")
        assert result["success"] is True, result
