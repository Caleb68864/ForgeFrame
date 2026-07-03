"""External oracle proofs for the real subtitle track + burn-in.

Two guarantees, both proven with pixels from real melt/ffmpeg -- neither can
pass by our parser and serializer agreeing with each other:

* **attach** -- an ``avfilter.subtitles`` track serialized onto the timeline
  tractor is (a) accepted by ``melt -consumer null`` and (b) actually rendered:
  the subtitle frame has visible text pixels while the control (no track) is a
  flat solid colour.  This refutes the plan's "subtitle properties may be
  app-rendered only" hedge for ``avfilter.subtitles``.
* **burn-in** -- ffmpeg's ``ass`` filter bakes caption pixels into a delivered
  file (the render-path guarantee that works regardless of project support).
"""
from __future__ import annotations

import statistics
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import subtitle_track as st

from . import builders
from ._oracle import melt_accepts, render_frame

# The external mark + tool gating come from conftest.py.

SRT = (
    "1\n00:00:00,000 --> 00:00:20,000\n"
    "HELLO SUBTITLE WORLD\nSECOND LINE HERE\n"
)


def _luma_stdev(png: Path) -> float:
    return statistics.pstdev(Image.open(png).convert("L").tobytes())


def _grey_project(title: str):
    # Mid-grey so white subtitle text has strong contrast either way.
    return builders.solid_color_project(color="0x808080ff", frames=60, title=title)


def test_attach_renders_subtitle_pixels(tmp_path, melt_bin, render_dir):
    """A serialized avfilter.subtitles track renders text; control does not."""
    # --- subtitle project: sidecar .ass next to the project, attached track ---
    sub_proj_path = tmp_path / "with_subs.kdenlive"
    sidecar = sub_proj_path.with_name(sub_proj_path.name + ".ass")
    sidecar.write_text(
        st.srt_to_ass(SRT, style=st.SubtitleStyle(size=48), width=320, height=180),
        encoding="utf-8",
    )
    sub_project = st.attach_subtitle(_grey_project("subs"), str(sidecar), name="en")
    serialize_project(sub_project, sub_proj_path)

    # --- control project: identical, no subtitle track ---
    ctl_proj_path = tmp_path / "no_subs.kdenlive"
    serialize_project(_grey_project("ctl"), ctl_proj_path)

    # (a) melt accepts the attached-subtitle project
    result = melt_accepts(sub_proj_path, melt_bin=melt_bin, frames=30)
    assert result.ok, f"melt rejected subtitle project:\n{result.stderr}"

    # (b) it actually renders subtitle pixels
    sub_frame = render_frame(sub_proj_path, 30, render_dir, melt_bin=melt_bin, name="sub.png")
    ctl_frame = render_frame(ctl_proj_path, 30, render_dir, melt_bin=melt_bin, name="ctl.png")

    ctl_std = _luma_stdev(ctl_frame)
    sub_std = _luma_stdev(sub_frame)
    assert ctl_std < 1.0, f"control frame should be flat, got stdev={ctl_std}"
    assert sub_std > 3.0, (
        f"subtitle frame should carry text pixels, got stdev={sub_std} "
        f"(control={ctl_std})"
    )


def test_burn_in_bakes_caption_pixels(tmp_path, ffmpeg_bin):
    """ffmpeg burn-in produces a file whose frames carry caption pixels."""
    from workshop_video_brain.edit_mcp.server.bundles.subtitle_track import (
        subtitles_burn_in,
    )

    ws = tmp_path / "ws"
    (ws / "media" / "processed").mkdir(parents=True, exist_ok=True)

    # A flat grey source clip (no captions).
    source = tmp_path / "grey.mp4"
    subprocess.run(
        [ffmpeg_bin, "-y", "-f", "lavfi", "-i",
         "color=c=0x808080:s=320x180:d=2:r=25", "-pix_fmt", "yuv420p", str(source)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    srt = tmp_path / "cap.srt"
    srt.write_text(SRT, encoding="utf-8")

    out = subtitles_burn_in(
        workspace_path=str(ws),
        project_file_or_media=str(source),
        srt_path=str(srt),
        style={"size": 40, "primary_color": "#FFFF00"},
    )
    assert out["status"] == "success", out
    burned = Path(out["data"]["output_path"])
    assert burned.exists()
    assert burned.parent == ws / "media" / "processed"

    # Extract a mid frame from each and compare variance.
    def _frame(video: Path, name: str) -> Path:
        png = tmp_path / name
        subprocess.run(
            [ffmpeg_bin, "-y", "-ss", "1", "-i", str(video), "-frames:v", "1", str(png)],
            capture_output=True, text=True, check=True, timeout=60,
        )
        return png

    ctl_std = _luma_stdev(_frame(source, "src.png"))
    burned_std = _luma_stdev(_frame(burned, "burned.png"))
    assert ctl_std < 1.0, f"source should be flat, got stdev={ctl_std}"
    assert burned_std > 3.0, (
        f"burned frame should carry caption pixels, got stdev={burned_std}"
    )
