"""melt + ffmpeg integration proofs for the review-loop pipeline (gap 5a / 5b).

Composes real render/extract/QC/PIL steps against synthetic fixtures:

- ``render_review_frames`` on a 2-clip colour project: exact frame count, a
  contact sheet, frames that differ across the cut (pixel compare), and a
  populated QC dict.
- ``thumbnail_generate`` on a testsrc frame with title text: text pixels present
  vs a no-text control, and a 1280-wide output.

Gated on melt + ffmpeg availability; skipped otherwise (matching the other
ffmpeg-guarded integration tests). Also asserts both MCP tools are registered
(``.fn``-unwrap).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from PIL import Image, ImageStat

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import review_loop as rl
from workshop_video_brain.edit_mcp.server.bundles.review_loop import (
    render_review_frames,
    thumbnail_generate,
)

melt_available = shutil.which("melt") is not None
ffmpeg_available = shutil.which("ffmpeg") is not None

pytestmark = pytest.mark.skipif(
    not (melt_available and ffmpeg_available),
    reason="melt and ffmpeg required for review-loop integration proofs",
)

# ``@mcp.tool()`` wraps the functions; ``.fn`` is the callable implementation.
_review = getattr(render_review_frames, "fn", render_review_frames)
_thumb = getattr(thumbnail_generate, "fn", thumbnail_generate)


def _two_clip_project(path: Path) -> None:
    """Red clip (0-2s) hard-cut to green clip (2-4s) at 25fps -> cut at t=2."""
    proj = KdenliveProject(
        version="7",
        title="ReviewLoop",
        profile=ProjectProfile(width=640, height=360, fps=25.0),
        producers=[
            Producer(
                id="red",
                resource="0xff0000ff",
                properties={"mlt_service": "color", "resource": "0xff0000ff", "length": "60"},
            ),
            Producer(
                id="green",
                resource="0x00ff00ff",
                properties={"mlt_service": "color", "resource": "0x00ff00ff", "length": "60"},
            ),
        ],
        tracks=[Track(id="v1", track_type="video")],
        playlists=[
            Playlist(
                id="v1",
                entries=[
                    PlaylistEntry(producer_id="red", in_point=0, out_point=49),
                    PlaylistEntry(producer_id="green", in_point=0, out_point=49),
                ],
            )
        ],
    )
    serialize_project(project=proj, output_path=path)


def _dominant(png: Path) -> tuple[float, float, float]:
    return tuple(ImageStat.Stat(Image.open(png).convert("RGB")).mean)  # type: ignore[return-value]


# --- 5a: render_review_frames ---------------------------------------------

def test_render_review_frames_extracts_looks_and_qc(tmp_path):
    proj = tmp_path / "cut.kdenlive"
    _two_clip_project(proj)

    out = _review(
        workspace_path=str(tmp_path),
        project_file=str(proj),
        every_seconds=2.0,
        width=320,
        run_qc=True,
        keep_render=False,
    )
    assert out["status"] == "success", out
    data = out["data"]

    # 4s clip, frame every 2s -> at least frames at t=0 (red) and t=2 (green).
    ts = data["timestamps"]
    assert ts[0] == 0.0 and 2.0 in ts, ts
    assert data["frame_count"] == len(ts) >= 2, data
    frames = [Path(p) for p in data["frame_paths"]]
    assert len(frames) == data["frame_count"] and all(f.exists() for f in frames)

    # Contact sheet exists.
    assert data["sheet_path"] and Path(data["sheet_path"]).exists()

    # Frames differ across the cut: t=0 frame is red-dominant, t=2 frame green.
    idx_after_cut = ts.index(2.0)
    r0, g0, b0 = _dominant(frames[0])
    r1, g1, b1 = _dominant(frames[idx_after_cut])
    assert r0 > g0 and r0 > b0, f"frame0 not red-dominant: {(r0, g0, b0)}"
    assert g1 > r1 and g1 > b1, f"post-cut frame not green-dominant: {(g1, r1, b1)}"
    # Explicit pixel-difference across the cut.
    assert abs(r0 - r1) > 40 or abs(g0 - g1) > 40

    # QC dict populated (a QCReport dump with the checks we know run).
    qc = data["qc"]
    assert isinstance(qc, dict) and qc, qc
    assert "checks_passed" in qc or "overall_pass" in qc, qc

    # keep_render=False -> render file dropped, frames retained.
    assert data["render_path"] is None
    assert data["duration"] > 3.5

    # Everything under reports/review/<timestamp>/.
    assert "reports/review/" in data["output_dir"].replace("\\", "/")


def test_render_review_frames_at_markers(tmp_path):
    """with every_seconds=0 and at_markers, frames come only from markers."""
    proj = tmp_path / "cut.kdenlive"
    _two_clip_project(proj)
    mdir = tmp_path / "markers"
    mdir.mkdir()
    (mdir / "x_markers.json").write_text(
        '[{"category": "chapter_candidate", "start_seconds": 2.5}]'
    )

    out = _review(
        workspace_path=str(tmp_path),
        project_file=str(proj),
        every_seconds=0,
        at_markers=True,
        width=160,
        run_qc=False,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["timestamps"] == [2.5], data["timestamps"]
    assert data["frame_count"] == 1


# --- 5b: thumbnail_generate ------------------------------------------------

def _make_testsrc_frame(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc=size=1280x720:rate=1:duration=1",
         "-frames:v", "1", str(path)],
        capture_output=True, text=True, check=True,
    )


def test_thumbnail_generate_overlays_text(tmp_path):
    src = tmp_path / "src.png"
    _make_testsrc_frame(src)

    # Control: same frame, no text.
    control = _thumb(
        workspace_path=str(tmp_path),
        source_or_project=str(src),
        at_seconds=0.0,
        text="",
        output_name="control",
        width=1280,
    )
    assert control["status"] == "success", control
    ctrl_path = Path(control["data"]["output_path"])
    assert control["data"]["width"] == 1280

    # With bold title text.
    withtext = _thumb(
        workspace_path=str(tmp_path),
        source_or_project=str(src),
        at_seconds=0.0,
        text="EPIC BUILD",
        subtitle="workshop day 1",
        style="thumbnail",
        output_name="thumb",
        width=1280,
    )
    assert withtext["status"] == "success", withtext
    tdata = withtext["data"]
    assert tdata["width"] == 1280
    txt_path = Path(tdata["output_path"])
    assert txt_path.exists()

    # Text proof: the bottom band (where the bold outlined title sits) changes
    # substantially vs the no-text control. White text + thick black outline
    # over a mid-grey testsrc drives up variation.
    ctrl_img = Image.open(ctrl_path).convert("L")
    txt_img = Image.open(txt_path).convert("L")
    assert ctrl_img.size == txt_img.size

    w, h = txt_img.size
    band = (0, int(h * 0.62), w, h)
    ctrl_band = ctrl_img.crop(band)
    txt_band = txt_img.crop(band)

    # Count pixels that differ notably between control and text bands.
    ctrl_px = list(ctrl_band.tobytes())
    txt_px = list(txt_band.tobytes())
    changed = sum(1 for a, b in zip(ctrl_px, txt_px) if abs(a - b) > 40)
    assert changed > 2000, f"too few changed pixels in text band: {changed}"

    # Near-black outline + near-white glyph pixels both present in the band.
    assert any(p < 20 for p in txt_px), "no dark outline pixels"
    assert any(p > 235 for p in txt_px), "no bright glyph pixels"


def test_thumbnail_generate_from_kdenlive_project(tmp_path):
    """Frame can be pulled straight from a .kdenlive via melt."""
    proj = tmp_path / "cut.kdenlive"
    _two_clip_project(proj)
    out = _thumb(
        workspace_path=str(tmp_path),
        source_or_project=str(proj),
        at_seconds=0.5,
        text="RED",
        output_name="proj_thumb",
        width=1280,
    )
    assert out["status"] == "success", out
    assert out["data"]["width"] == 1280
    assert Path(out["data"]["output_path"]).exists()


# --- registration asserts --------------------------------------------------

def test_tools_registered():
    import asyncio

    import workshop_video_brain.server as server_mod

    mcp = server_mod.mcp
    getter = getattr(mcp, "get_tools", None) or getattr(mcp, "list_tools")
    result = asyncio.run(getter())
    names = set(result) if isinstance(result, dict) else {t.name for t in result}
    assert "render_review_frames" in names
    assert "thumbnail_generate" in names
    assert callable(_review) and callable(_thumb)
