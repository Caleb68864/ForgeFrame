"""melt render check for title cards (§6 / §2 ``test_title_renders``).

Builds a title over a solid colour clip, renders a mid-card frame with melt, and
asserts that bright text pixels are present (the card actually rendered) — an
oracle outside our own parser/serializer.  Gated on melt + ffmpeg availability;
skipped otherwise (matching the ffmpeg-guarded integration tests).

NOTE: a standalone ``kdenlivetitle`` producer flattens its item layer onto black
when rendered directly; the card only composites correctly *over a track below*.
The title_card_add tool always places the card on a top track over footage, so
this test renders through the same composite path.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server.bundles.titles import title_card_add

# ``@mcp.tool()`` wraps the function; ``.fn`` is the callable implementation.
_add = getattr(title_card_add, "fn", title_card_add)

melt_available = shutil.which("melt") is not None
ffmpeg_available = shutil.which("ffmpeg") is not None

pytestmark = pytest.mark.skipif(
    not (melt_available and ffmpeg_available),
    reason="melt and ffmpeg required for title render check",
)


def _base_color_project(path: Path) -> None:
    proj = KdenliveProject(
        version="7",
        title="RenderTitle",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(
                id="bg",
                resource="0x004488ff",
                properties={"mlt_service": "color", "resource": "0x004488ff", "length": "50"},
            )
        ],
        tracks=[Track(id="v1", track_type="video")],
        playlists=[
            Playlist(id="v1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=49)])
        ],
    )
    serialize_project(project=proj, output_path=path)


def _render_frame(project: Path, frame: int, out_dir: Path) -> Path | None:
    for f in glob.glob(str(out_dir / "f_*.png")):
        os.remove(f)
    subprocess.run(
        ["melt", str(project), f"out={frame}", "-consumer", f"avformat:{out_dir}/f_%03d.png"],
        capture_output=True,
        text=True,
    )
    frames = sorted(glob.glob(str(out_dir / "f_*.png")))
    return Path(frames[-1]) if frames else None


def _stats(png: Path, out_dir: Path, crop: tuple[int, int, int, int] | None = None) -> dict:
    sf = out_dir / "stats.txt"
    vf = f"signalstats,metadata=print:file={sf}"
    if crop:
        vf = "crop={}:{}:{}:{},".format(*crop) + vf
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(png), "-vf", vf, "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    return dict(re.findall(r"lavfi\.signalstats\.(\w+)=([\d.]+)", sf.read_text()))


def test_title_card_renders_text_pixels(tmp_path):
    proj = tmp_path / "render.kdenlive"
    _base_color_project(proj)

    out = _add(
        project_file=str(proj),
        text="HELLO WORLD",
        subtitle="Render Check",
        style="lower-third",
        at_seconds=0.0,
        duration_seconds=1.2,
        track=None,
    )
    assert out["status"] == "success", out

    frame = _render_frame(proj, 15, tmp_path)
    assert frame is not None, "melt produced no frame"

    full = _stats(frame, tmp_path)
    # Bright text pixels present somewhere in the frame (bg is mid-blue ~Y60).
    assert int(float(full["YMAX"])) > 200, f"no bright pixels: {full}"

    # And specifically in the lower-third text band.
    band = _stats(frame, tmp_path, crop=(1400, 200, 200, 760))
    assert int(float(band["YMAX"])) > 200, f"no text in lower-third band: {band}"
