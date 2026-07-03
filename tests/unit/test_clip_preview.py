"""Unit tests for the clip-preview command pipeline (pure functions)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines import clip_preview as cp


class TestOutputName:
    def test_gif_name(self):
        assert cp.preview_output_name("shotA", "gif") == "shotA_preview.gif"

    def test_mp4_name(self):
        assert cp.preview_output_name("shotA", "mp4") == "shotA_preview.mp4"


class TestExpectedFrameCount:
    def test_basic(self):
        assert cp.expected_frame_count(3.0, 8) == 24

    def test_rounds(self):
        assert cp.expected_frame_count(2.5, 7) == 18  # 17.5 -> 18

    def test_minimum_one(self):
        assert cp.expected_frame_count(0.01, 1) == 1


class TestPalettegenCommand:
    def test_shape(self):
        cmd = cp.palettegen_command(
            Path("/in/c.mp4"), Path("/tmp/p.png"), 3.0, 8, 320
        )
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert cmd[cmd.index("-t") + 1] == "3.0000"
        vf = cmd[cmd.index("-vf") + 1]
        assert "fps=8" in vf
        assert "scale=320:-2:flags=lanczos" in vf
        assert vf.endswith("palettegen")
        assert cmd[-1] == "/tmp/p.png"


class TestPaletteuseCommand:
    def test_shape(self):
        cmd = cp.paletteuse_command(
            Path("/in/c.mp4"), Path("/tmp/p.png"), Path("/out/o.gif"),
            3.0, 8, 320,
        )
        assert cmd.count("-i") == 2  # source + palette
        lavfi = cmd[cmd.index("-lavfi") + 1]
        assert "paletteuse" in lavfi
        assert "fps=8" in lavfi
        assert cmd[cmd.index("-loop") + 1] == "0"
        assert cmd[-1] == "/out/o.gif"


class TestMp4PreviewCommand:
    def test_shape(self):
        cmd = cp.mp4_preview_command(
            Path("/in/c.mp4"), Path("/out/o.mp4"), 2.0, 10, 240
        )
        assert "-an" in cmd  # muted
        assert cmd[cmd.index("-c:v") + 1] == "libx264"
        assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
        vf = cmd[cmd.index("-vf") + 1]
        assert "fps=10" in vf and "scale=240:-2" in vf
        assert cmd[-1] == "/out/o.mp4"


class TestSupportedFormats:
    def test_contains_gif_and_mp4(self):
        assert cp.SUPPORTED_FORMATS == frozenset({"gif", "mp4"})
