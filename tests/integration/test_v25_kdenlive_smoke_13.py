"""Smoke test batch 13.0: avfilter colour-grade and artistic families.

Smoke 027 / batch 12 verified the generic ``avfilter.X`` EntryFilter
shape works in Kdenlive 25.x across zero-param, scalar, matrix, and
keyframed parameter modes.  This batch covers the high-value
colour-grade and artistic filters that actual editing workflows
need (vs the long-tail avfilter family the audit calls out).

* **041 eq** -- ffmpeg's ``eq`` filter for brightness/contrast/
  saturation/gamma adjustments.  The bread-and-butter exposure
  correction primitive; complements 030's lift_gamma_gain 3-way.
* **042 huesaturation** -- HSL-style hue rotation + saturation
  adjustment.  Used for selective colour grading.
* **043 curves** -- ffmpeg's ``curves`` filter with named presets
  (``vintage``, ``increase_contrast``, etc.).  The most common
  artistic grade in stock footage workflows.
* **044 boxblur** -- alternative blur to gblur (027) -- separable
  box kernel, faster than gaussian for large radii.
* **045 chromahold** -- desaturate everything except a target colour
  (the "schindler's list red dress" effect).  Useful for emphasising
  branded colour in product b-roll.
* **046 edgedetect** -- ffmpeg's edge-detect filter for an artistic
  graphic-novel look.

All scalar parameters in this batch use the same proven shape; if
all six smokes open clean, the avfilter colour-grade bridge is
verified.
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
# 041 -- avfilter.eq exposure correction (warm + slightly contrasty)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_041_avfilter_eq_warm_contrasty():
    """Brighten + add contrast + saturation bump.  ``eq`` is ffmpeg's
    general-purpose exposure primitive.  Values picked to be
    obviously visible vs the source (mild values are easy to miss)."""
    project, entry, _ = _project_with_clip("smoke_041_eq")
    entry.filters.append(
        EntryFilter(
            id="avfilter_eq",
            properties={
                "mlt_service": "avfilter.eq",
                "kdenlive_id": "avfilter.eq",
                "av.brightness": "0.25",   # clearly brighter (-1..1)
                "av.contrast": "1.6",      # strong contrast bump (0..2)
                "av.saturation": "1.8",    # vivid saturation (0..3)
                "av.gamma": "1.0",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "041-avfilter-eq-warm-contrasty.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 042 -- avfilter.huesaturation (cool the image, mild teal-shift)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_042_avfilter_huesaturation_teal_shift():
    """Hue rotation + saturation bump.  ffmpeg's huesaturation needs
    ``strength`` to be > 0 for ANY of the other params to take effect
    -- that's the trap.  At strength=0 (the silent default) the panel
    shows hue/saturation values but the effect does nothing visually.
    Set strength=1 explicitly to ensure the user sees the effect."""
    project, entry, _ = _project_with_clip("smoke_042_huesaturation")
    entry.filters.append(
        EntryFilter(
            id="avfilter_huesaturation",
            properties={
                "mlt_service": "avfilter.huesaturation",
                "kdenlive_id": "avfilter.huesaturation",
                "av.hue": "-90",
                "av.saturation": "0.6",
                "av.intensity": "0",
                "av.strength": "1",  # critical: must be > 0
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "042-avfilter-huesaturation-teal-shift.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 043 -- avfilter.curves with named "vintage" preset
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_043_frei0r_curves():
    """Curves grade via ``frei0r.curves`` (NOT ``avfilter.curves``,
    which Kdenlive 25.x's effect registry doesn't recognise).

    The frei0r.curves filter encodes its 4 control points across
    NUMBERED properties (1-15), NOT just the simple kdenlive:curve
    string -- if you only set the curve string the plugin reads
    uninitialised junk from the numbered properties and produces a
    flatline-at-white curve.  Copy ALL the numbered props from a
    verified-working filter.

    These values are taken verbatim from upstream
    ``avfilter-curves.kdenlive`` (a gentle S-curve that lifts
    shadows slightly + compresses highlights)."""
    project, entry, _ = _project_with_clip("smoke_043_curves")
    entry.filters.append(
        EntryFilter(
            id="frei0r_curves",
            properties={
                "version": "0.4",
                "mlt_service": "frei0r.curves",
                "kdenlive_id": "frei0r.curves",
                "Channel": "0.5",    # luma channel
                # Numbered props 1-15 are the control point + curve-type
                # encoding the frei0r plugin actually reads at render
                # time.  These mirror the upstream working filter.
                "1": "1",
                "2": "0.1",
                "3": "0.4",
                "4": "1",
                "6": "0",
                "7": "0",
                "8": "0.136364",
                "9": "0.248062",
                "10": "0.909091",
                "11": "0.844961",
                "12": "1",
                "13": "1",
                "14": "0",
                "15": "0",
                "kdenlive:curve": "0/0;0.136364/0.248062;0.909091/0.844961;1/1;",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "043-avfilter-curves-vintage.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 044 -- avfilter.boxblur (large-radius separable blur)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_044_native_box_blur():
    """Native MLT ``box_blur`` filter (Kdenlive UI label: "Planes Blur").
    ``avfilter.boxblur`` loads but Kdenlive's UI munges its parameters
    in confusing ways (luma_power gets stuck at 0 = no blur).  The
    native filter takes plain hradius/vradius/iterations and is what
    Kdenlive's "Planes Blur" effect actually wraps."""
    project, entry, _ = _project_with_clip("smoke_044_boxblur")
    entry.filters.append(
        EntryFilter(
            id="native_box_blur",
            properties={
                "mlt_service": "box_blur",
                "kdenlive_id": "box_blur",
                "hradius": "20",
                "vradius": "20",
                "iterations": "1",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "044-avfilter-boxblur.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 045 -- avfilter.chromahold (keep red, desaturate the rest)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_045_avfilter_chromahold_keep_orange():
    """Keep orange, desaturate everything else.  The test source clip
    has an orange butterfly on green foliage with white flowers --
    chromahold-keep-red would have nothing to highlight (no red),
    but keeping ORANGE lights up the butterfly while desaturating
    leaves and flowers.  Similarity bumped to 0.5 + blend 0.4 so the
    effect is obvious; the original 0.25/0.10 was barely visible."""
    project, entry, _ = _project_with_clip("smoke_045_chromahold")
    entry.filters.append(
        EntryFilter(
            id="avfilter_chromahold",
            properties={
                "mlt_service": "avfilter.chromahold",
                "kdenlive_id": "avfilter.chromahold",
                "av.color": "orange",
                "av.similarity": "0.5",
                "av.blend": "0.4",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "045-avfilter-chromahold-red.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 046 -- avfilter.edgedetect (graphic-novel look via Canny)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_046_avfilter_edgedetect_canny():
    """Canny edge detection for graphic-novel/comic-book style.
    Useful for stylising B-roll in artistic montages."""
    project, entry, _ = _project_with_clip("smoke_046_edgedetect")
    entry.filters.append(
        EntryFilter(
            id="avfilter_edgedetect",
            properties={
                "mlt_service": "avfilter.edgedetect",
                "kdenlive_id": "avfilter.edgedetect",
                "av.low": "0.1",
                "av.high": "0.4",
                "av.mode": "canny",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "046-avfilter-edgedetect-canny.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
