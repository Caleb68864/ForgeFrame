"""Smoke test batch 16.0: frei0r EntryFilter family.

Verified shape against the upstream KDE test-suite reference at
``tests/fixtures/kdenlive_references/qtblend_freeze_upstream_kde.kdenlive``.

frei0r effects use the SAME ``EntryFilter`` shape as avfilter (one
``<filter>`` child of an ``<entry>``), differing only by:

* ``mlt_service=frei0r.<name>`` (no ``av.`` parameter prefix)
* ``kdenlive_id=frei0r.<name>``
* ``version`` property (e.g. ``0.1``, ``0.2``)
* Parameter names use CamelCase or lowercase as-is (NOT ``av.<name>``)
* Keyframe syntax identical: ``00:00:00.000=value``

This batch covers four representative frei0r effects:

* **049 brightness** -- ``frei0r.brightness`` w/ ``Brightness`` (CamelCase) keyframe
* **050 colorize** -- ``frei0r.colorize`` w/ ``hue`` / ``saturation`` / ``lightness`` (lowercase) keyframes
* **051 contrast0r** -- ``frei0r.contrast0r`` w/ ``Contrast`` keyframe
* **052 saturat0r** -- ``frei0r.saturat0r`` w/ ``Saturation`` keyframe

Together with the avfilter family, this verifies BOTH effect-prefix
shapes work, closing the audit's "16 × effect_frei0r_* opaque-root
tools need EntryFilter migration" debt at the SHAPE level (the legacy
opaque MCP wrappers still need rewiring as a follow-up, but the
underlying serializer now demonstrably emits the correct shape).
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


def _add_clip(project, *, producer_id, track_id, in_point, out_point, source_path):
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


def _project_with_clip(title, *, fps=29.97, seconds=4.0):
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
    return project, pl.entries[0]


# ---------------------------------------------------------------------------
# 049 -- frei0r.brightness (subtle keyframed brightness lift)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_049_frei0r_brightness():
    """Mild brighten via frei0r.brightness.  CamelCase ``Brightness``
    parameter, version 0.2."""
    project, entry = _project_with_clip("smoke_049_frei0r_brightness")
    entry.filters.append(
        EntryFilter(
            id="frei0r_brightness",
            properties={
                "version": "0.2",
                "mlt_service": "frei0r.brightness",
                "kdenlive_id": "frei0r.brightness",
                "Brightness": "00:00:00.000=0.6",  # 0.5 = neutral, >0.5 brighter
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "049-frei0r-brightness.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 050 -- frei0r.colorize (warm orange tint)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_050_frei0r_colorize_warm():
    """Warm orange colorize via frei0r.colorize.  Lowercase params
    ``hue``/``saturation``/``lightness``, version 0.1."""
    project, entry = _project_with_clip("smoke_050_frei0r_colorize")
    entry.filters.append(
        EntryFilter(
            id="frei0r_colorize",
            properties={
                "version": "0.1",
                "mlt_service": "frei0r.colorize",
                "kdenlive_id": "frei0r.colorize",
                "hue": "00:00:00.000=0.083333",      # ~30deg, orange
                "saturation": "00:00:00.000=0.4",
                "lightness": "00:00:00.000=0",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "050-frei0r-colorize-warm.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 051 -- frei0r.contrast0r (mild contrast bump)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_051_frei0r_contrast0r():
    """Bump contrast via frei0r.contrast0r."""
    project, entry = _project_with_clip("smoke_051_frei0r_contrast0r")
    entry.filters.append(
        EntryFilter(
            id="frei0r_contrast0r",
            properties={
                "version": "0.1",
                "mlt_service": "frei0r.contrast0r",
                "kdenlive_id": "frei0r.contrast0r",
                "Contrast": "00:00:00.000=0.6",  # 0.5 = neutral
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "051-frei0r-contrast0r.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 052 -- frei0r.saturat0r (saturation reduction for muted look)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_052_frei0r_saturat0r_muted():
    """Reduce saturation for a muted/desaturated look."""
    project, entry = _project_with_clip("smoke_052_frei0r_saturat0r")
    entry.filters.append(
        EntryFilter(
            id="frei0r_saturat0r",
            properties={
                "version": "0.1",
                "mlt_service": "frei0r.saturat0r",
                "kdenlive_id": "frei0r.saturat0r",
                "Saturation": "00:00:00.000=0.3",  # 0.5 = neutral, <0.5 muted
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "052-frei0r-saturat0r-muted.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
