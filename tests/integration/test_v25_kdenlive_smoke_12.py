"""Smoke test batch 12.0: avfilter family extensions.

Smoke 027 already proved the generic ``avfilter.X`` EntryFilter shape
opens cleanly in Kdenlive 25.x using ``avfilter.gblur``.  Every other
``avfilter.*`` filter in the KDE test suite has the same XML shape,
varying only by service name and parameter set (see the audit at
``vault/wiki/kdenlive-test-suite-coverage-audit.md`` -- this batch
covers ~30 ``avfilter-*.kdenlive`` files at once).

These smokes verify a representative sample across the three
families flagged in the audit:

* **Geometry** (035 hflip, 036 crop) -- ``avfilter.hflip`` /
  ``avfilter.crop``.  hflip has zero parameters; crop takes pixel
  coords.
* **Stylise** (037 sepia, 038 invert) -- ``avfilter.colorchannelmixer``
  with sepia coefficients, ``avfilter.negate`` for invert.  Both are
  scalar-param, no keyframes.
* **Drawing** (039 drawbox, 040 drawgrid) -- ``avfilter.drawbox`` and
  ``avfilter.drawgrid``.  Used for branding overlays / safe-area
  frames.  All scalar params (x, y, w, h, color, thickness).

The failure mode for any of these in Kdenlive 25.x would show the
filter loaded but with the "Effect not supported" warning -- if all
six smoke outputs open clean and apply visibly, the avfilter bridge
is verified across the audit's long-tail.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    EntryFilter,
    KdenliveProject,
    Playlist,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")
USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")


def _build_initial_project(title: str, fps: float = 29.97) -> KdenliveProject:
    project = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
    )
    project.tracks = [
        Track(id="playlist_video", track_type="video", name="V1"),
        Track(id="playlist_audio", track_type="audio", name="A1"),
    ]
    project.playlists = [
        Playlist(id="playlist_video"),
        Playlist(id="playlist_audio"),
    ]
    project.tractor = {"id": "main_seq", "in": "0", "out": "0"}
    return project


def _add_clip(
    project: KdenliveProject,
    *,
    producer_id: str,
    track_id: str,
    in_point: int,
    out_point: int,
    source_path: str,
) -> KdenliveProject:
    return patch_project(
        project,
        [
            AddClip(
                producer_id=producer_id,
                track_ref=track_id,
                track_id=track_id,
                in_point=in_point,
                out_point=out_point,
                position=-1,
                source_path=source_path,
            )
        ],
    )


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


def _project_with_clip(title: str, *, fps: float = 29.97, seconds: float = 4.0):
    """Returns (project, entry, clip_path) ready to receive an EntryFilter,
    or skips the test if no clip is available."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    duration = int(seconds * fps)
    project = _build_initial_project(title, fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    return project, pl.entries[0], clip


# ---------------------------------------------------------------------------
# 035 -- avfilter.hflip (horizontal flip)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_035_avfilter_hflip():
    """Mirror the clip horizontally.  Zero-parameter avfilter; the
    presence of the filter alone triggers ffmpeg's ``hflip`` op."""
    project, entry, _ = _project_with_clip("smoke_035_hflip")
    entry.filters.append(
        EntryFilter(
            id="avfilter_hflip",
            properties={
                "mlt_service": "avfilter.hflip",
                "kdenlive_id": "avfilter.hflip",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "035-avfilter-hflip.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 036 -- avfilter.crop (centred 1280x720 crop from 1920x1080 source)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_036_avfilter_crop_centered():
    """Crop the clip to a centred 1280x720 window.  All scalar params
    (no keyframes).  Useful for re-framing a 16:9 source for a
    different aspect ratio without leaving qtblend territory."""
    project, entry, _ = _project_with_clip("smoke_036_crop")
    entry.filters.append(
        EntryFilter(
            id="avfilter_crop",
            properties={
                "mlt_service": "avfilter.crop",
                "kdenlive_id": "avfilter.crop",
                "av.w": "1280",
                "av.h": "720",
                # x/y default to (in_w-out_w)/2 / (in_h-out_h)/2 in ffmpeg,
                # so omitting them produces a centred crop -- exactly what
                # we want for a smoke test.
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "036-avfilter-crop-centered.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 037 -- avfilter.colorchannelmixer with sepia coefficients
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_037_avfilter_sepia_via_colorchannelmixer():
    """Apply a sepia tone using the standard colour-matrix coefficients.
    ``avfilter.colorchannelmixer`` is more general than dedicated
    ``sepia`` filters (which only exist in mlt-core, not avfilter), so
    we use the matrix form which is widely supported."""
    project, entry, _ = _project_with_clip("smoke_037_sepia")
    entry.filters.append(
        EntryFilter(
            id="avfilter_sepia",
            properties={
                "mlt_service": "avfilter.colorchannelmixer",
                "kdenlive_id": "avfilter.colorchannelmixer",
                "av.rr": "0.393",
                "av.rg": "0.769",
                "av.rb": "0.189",
                "av.gr": "0.349",
                "av.gg": "0.686",
                "av.gb": "0.168",
                "av.br": "0.272",
                "av.bg": "0.534",
                "av.bb": "0.131",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "037-avfilter-sepia.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 038 -- avfilter.negate (colour invert)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_038_avfilter_negate():
    """Photographic colour negative via ffmpeg's ``negate`` filter.
    Zero parameters."""
    project, entry, _ = _project_with_clip("smoke_038_negate")
    entry.filters.append(
        EntryFilter(
            id="avfilter_negate",
            properties={
                "mlt_service": "avfilter.negate",
                "kdenlive_id": "avfilter.negate",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "038-avfilter-negate.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 039 -- avfilter.drawbox (red 200x200 box at top-left for branding)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_039_avfilter_drawbox():
    """Draw a filled red rectangle for a brand-bug overlay test.
    All scalar params; thickness=fill paints the interior."""
    project, entry, _ = _project_with_clip("smoke_039_drawbox")
    entry.filters.append(
        EntryFilter(
            id="avfilter_drawbox",
            properties={
                "mlt_service": "avfilter.drawbox",
                "kdenlive_id": "avfilter.drawbox",
                "av.x": "100",
                "av.y": "100",
                "av.w": "200",
                "av.h": "200",
                "av.color": "red@0.6",
                "av.thickness": "fill",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "039-avfilter-drawbox.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 040 -- avfilter.drawgrid (rule-of-thirds overlay for safe-area framing)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_040_avfilter_drawgrid_thirds():
    """Rule-of-thirds grid overlay (1920/3 = 640 wide, 1080/3 = 360 tall).
    Useful for framing reference during review cuts -- not for final
    output."""
    project, entry, _ = _project_with_clip("smoke_040_drawgrid")
    entry.filters.append(
        EntryFilter(
            id="avfilter_drawgrid",
            properties={
                "mlt_service": "avfilter.drawgrid",
                "kdenlive_id": "avfilter.drawgrid",
                "av.x": "0",
                "av.y": "0",
                "av.w": "640",
                "av.h": "360",
                "av.color": "white@0.4",
                "av.thickness": "2",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "040-avfilter-drawgrid-thirds.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
