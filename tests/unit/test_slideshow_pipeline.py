"""Unit tests for the slideshow pipeline pure functions.

Covers timing math, numbered-sequence detection, backend selection, mixed
extension handling and FFmpeg command construction (no FFmpeg execution).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import slideshow as ss


# ---------------------------------------------------------------------------
# Timing math
# ---------------------------------------------------------------------------

class TestTimingMath:
    def test_fps_per_image_converts_via_project_fps(self):
        # 6 frames held at 25 fps => 0.24 s on screen
        assert ss.resolve_per_image_seconds(6, None, 25.0) == pytest.approx(0.24)

    def test_explicit_seconds_overrides_fps_per_image(self):
        assert ss.resolve_per_image_seconds(6, 2.0, 25.0) == 2.0

    def test_zero_project_fps_raises(self):
        with pytest.raises(ValueError):
            ss.resolve_per_image_seconds(6, None, 0.0)

    def test_non_positive_duration_raises(self):
        with pytest.raises(ValueError):
            ss.resolve_per_image_seconds(6, -1.0, 25.0)

    def test_total_duration_hard_cut(self):
        assert ss.compute_total_duration(5, 2.0, 0.0) == 10.0

    def test_total_duration_with_crossfade(self):
        # 5 * 2.0 - 4 * 0.5 = 8.0
        assert ss.compute_total_duration(5, 2.0, 0.5) == 8.0

    def test_total_duration_empty(self):
        assert ss.compute_total_duration(0, 2.0, 0.0) == 0.0

    def test_frames_per_image_floor_of_one(self):
        assert ss.frames_per_image(0.001, 25.0) == 1
        assert ss.frames_per_image(0.24, 25.0) == 6


# ---------------------------------------------------------------------------
# Sequence detection & backend selection
# ---------------------------------------------------------------------------

class TestSequenceDetection:
    def test_uniform_contiguous_sequence(self):
        paths = [Path(f"frame{i:03d}.png") for i in range(1, 6)]
        result = ss.detect_numbered_sequence(paths)
        assert result == ("frame%03d.png", 1, 5)

    def test_non_contiguous_returns_none(self):
        paths = [Path("frame001.png"), Path("frame003.png")]
        assert ss.detect_numbered_sequence(paths) is None

    def test_mixed_extension_returns_none(self):
        paths = [Path("a001.png"), Path("a002.jpg")]
        assert ss.detect_numbered_sequence(paths) is None

    def test_mixed_prefix_returns_none(self):
        paths = [Path("a001.png"), Path("b002.png")]
        assert ss.detect_numbered_sequence(paths) is None

    def test_start_number_preserved(self):
        paths = [Path("img010.png"), Path("img011.png"), Path("img012.png")]
        assert ss.detect_numbered_sequence(paths) == ("img%03d.png", 10, 3)

    def test_backend_pattern_for_uniform(self):
        paths = [Path(f"f{i:02d}.png") for i in range(3)]
        assert ss.choose_backend(paths, crossfade_frames=0, kenburns=False) == "pattern"

    def test_backend_filtergraph_for_mixed(self):
        paths = [Path("cat.png"), Path("dog.jpg")]
        assert ss.choose_backend(paths, crossfade_frames=0, kenburns=False) == "filtergraph"

    def test_backend_filtergraph_when_crossfade(self):
        paths = [Path("f00.png"), Path("f01.png")]
        assert ss.choose_backend(paths, crossfade_frames=10, kenburns=False) == "filtergraph"

    def test_backend_filtergraph_when_kenburns(self):
        paths = [Path("f00.png"), Path("f01.png")]
        assert ss.choose_backend(paths, crossfade_frames=0, kenburns=True) == "filtergraph"


# ---------------------------------------------------------------------------
# Image listing (mixed extensions)
# ---------------------------------------------------------------------------

class TestListImages:
    def test_lists_and_natural_sorts(self, tmp_path):
        for name in ["img10.png", "img2.png", "img1.png", "notes.txt"]:
            (tmp_path / name).write_bytes(b"x")
        result = [p.name for p in ss.list_images(tmp_path)]
        assert result == ["img1.png", "img2.png", "img10.png"]

    def test_accepts_mixed_image_extensions(self, tmp_path):
        for name in ["a.png", "b.jpg", "c.jpeg", "d.webp", "ignore.md"]:
            (tmp_path / name).write_bytes(b"x")
        result = {p.name for p in ss.list_images(tmp_path)}
        assert result == {"a.png", "b.jpg", "c.jpeg", "d.webp"}

    def test_empty_for_missing_folder(self, tmp_path):
        assert ss.list_images(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

class TestPatternCommand:
    def test_pattern_command_structure(self):
        cmd = ss.build_pattern_command(
            Path("/imgs"), "frame%03d.png", 1, Path("/out.mp4"),
            1280, 720, 25.0, 0.24,
        )
        assert cmd[0] == "ffmpeg"
        assert "-framerate" in cmd
        # fps 25 / 6 frames-per-image => input rate 25/6
        assert cmd[cmd.index("-framerate") + 1] == "25/6"
        assert cmd[cmd.index("-start_number") + 1] == "1"
        assert cmd[cmd.index("-i") + 1] == str(Path("/imgs/frame%03d.png"))
        vf = cmd[cmd.index("-vf") + 1]
        assert "scale=1280:720" in vf and "pad=1280:720" in vf
        assert cmd[-1] == "/out.mp4"
        assert "libx264" in cmd

    def test_pattern_command_start_number(self):
        cmd = ss.build_pattern_command(
            Path("/imgs"), "img%05d.png", 42, Path("/o.mp4"),
            1920, 1080, 30.0, 1.0,
        )
        assert cmd[cmd.index("-start_number") + 1] == "42"


class TestFiltergraphCommand:
    def test_concat_hard_cut(self):
        paths = [Path("/a.png"), Path("/b.jpg"), Path("/c.png")]
        cmd = ss.build_filtergraph_command(
            paths, Path("/out.mp4"), 1280, 720, 25.0, 0.5,
        )
        assert cmd.count("-i") == 3
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=n=3:v=1:a=0" in fc
        assert "xfade" not in fc
        # each still looped for its duration
        assert cmd.count("-loop") == 3
        assert cmd[cmd.index("-map") + 1] == "[xfout]"

    def test_crossfade_uses_xfade(self):
        paths = [Path("/a.png"), Path("/b.png"), Path("/c.png")]
        cmd = ss.build_filtergraph_command(
            paths, Path("/out.mp4"), 1280, 720, 25.0, 2.0,
            crossfade_seconds=0.5,
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert fc.count("xfade") == 2  # n-1 transitions
        assert "concat=" not in fc
        # offsets accumulate: first at per-image - crossfade = 1.5
        assert "offset=1.500000" in fc

    def test_kenburns_uses_zoompan_single_frame_inputs(self):
        paths = [Path("/a.png"), Path("/b.png")]
        cmd = ss.build_filtergraph_command(
            paths, Path("/out.mp4"), 1920, 1080, 25.0, 1.0,
            kenburns=True,
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert fc.count("zoompan") == 2
        assert "crop=1920:1080" in fc
        # Ken Burns feeds single frames (no -loop/-t)
        assert "-loop" not in cmd

    def test_single_image_no_concat(self):
        cmd = ss.build_filtergraph_command(
            [Path("/a.png")], Path("/out.mp4"), 640, 480, 25.0, 1.0,
        )
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "concat=" not in fc and "xfade" not in fc
        assert cmd[cmd.index("-map") + 1] == "[v0]"

    def test_empty_paths_raises(self):
        with pytest.raises(ValueError):
            ss.build_filtergraph_command(
                [], Path("/out.mp4"), 640, 480, 25.0, 1.0,
            )
