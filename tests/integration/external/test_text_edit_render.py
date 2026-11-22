"""Real melt: media_text_edit's .kdenlive renders the 3.5 s edit with sound at the source profile (prompt 38)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_melt_ffmpeg
from tests.integration.test_media_text_edit import CLIP, write_transcript
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.server.tools.text_edit import media_text_edit

from ._oracle import audio_stats, probe, render_video

pytestmark = [pytest.mark.external, requires_melt_ffmpeg]


def test_kdenlive_output_renders_the_edit(melt_bin, tmp_path, render_dir):
    t = write_transcript(tmp_path / "t.json")
    result = call_tool(media_text_edit, str(CLIP), str(t), delete='[{"words": [3, 5]}]', output="kdenlive",
                       output_dir=str(tmp_path))
    assert result["status"] == "success", result
    project_path = Path(result["data"]["paths"]["kdenlive"])
    profile = parse_project(project_path).profile
    assert (profile.width, profile.height) == (1920, 1080) and profile.fps == pytest.approx(30000 / 1001, abs=0.01)
    out = render_video(project_path, render_dir / "edit.mp4", 140, melt_bin=melt_bin)
    assert probe(out).duration == pytest.approx(3.5, abs=0.1)
    assert audio_stats(out)["RMS level dB"] > -60
