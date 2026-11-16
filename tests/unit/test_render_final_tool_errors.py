"""render_final_tool maps a bad argument to invalid_input.

Before 5d45713 a ValueError (e.g. ``output_name`` containing a directory)
fell through to the generic "Confirm melt and ffmpeg are installed" message,
which sends the caller after the wrong cause. That commit added the mapping
without a test; this is it. No melt/ffmpeg is run: the codec probe is
stubbed and the ValueError is raised before any render starts.
"""
from __future__ import annotations

from tests._testkit import call_tool
from workshop_video_brain.edit_mcp.pipelines import render_final as render_final_pipeline
from workshop_video_brain.edit_mcp.server.tools import render


def test_output_name_with_directory_is_invalid_input(tmp_path, monkeypatch):
    monkeypatch.setattr(render_final_pipeline, "check_codec_available", lambda _c: True)
    working = tmp_path / "projects" / "working_copies"
    working.mkdir(parents=True)
    (working / "demo_v1.kdenlive").write_text("<mlt/>")

    result = call_tool(
        render.render_final_tool, str(tmp_path), "youtube-1080p", output_name="sub/x",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_input", result
    assert "output_name" in result["message"]
    assert "melt" not in result.get("suggestion", "")
