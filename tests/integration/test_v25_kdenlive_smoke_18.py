"""Smoke test batch 18.0: native MLT effects -- keying + dynamic text/timer.

Verified shape against the upstream KDE test-suite reference at
``tests/fixtures/kdenlive_references/mlt_plus_video_effects_upstream_kde.kdenlive``.

These are the native MLT effects that DON'T sit under either the
``avfilter.<name>`` or ``frei0r.<name>`` prefixes -- they have bare
``mlt_service`` names but otherwise use the same ``EntryFilter`` shape
as the rest of the per-clip filter family.

* **054 chroma** -- ``mlt_service=chroma``, native green/blue-screen
  keying.  ``key`` carries hex-colour keyframes (e.g.
  ``00:00:00.000=0x00ff00ff`` for opaque green); ``variance`` is the
  scalar tolerance.
* **055 lumakey** -- ``mlt_service=lumakey``, key by luminance.  Scalar
  ``threshold``/``slope``/``prelevel``/``postlevel``.  Useful for
  black/white masking.
* **056 dynamictext** -- ``mlt_service=dynamictext``, MLT's tag-replaced
  text overlay.  The ``argument`` property carries the template (e.g.
  ``"#timecode# - #frame#"``), and ``geometry`` positions the text box.
* **057 timer** -- ``mlt_service=timer``, count-up/down clock overlay.
  ``format`` (e.g. ``"MM:SS.SSS"``), ``start``, ``duration``, ``offset``,
  ``direction``.

These cover the audit's ``Chroma / luma keying (native MLT)``,
``Dynamic text & timer`` rows.  Same EntryFilter shape, no serializer
changes needed -- just exercise the existing per-entry filter path with
verified-shape parameter sets.
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
# 054 -- native chroma key (green-screen)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_054_chroma_key_green():
    """Chroma key out pure green (0x00ff00).  Used for green-screen
    compositing.  ``key`` is a keyframe string of hex colours
    (RGBA in 0xRRGGBBAA form); ``variance`` is the tolerance."""
    project, entry = _project_with_clip("smoke_054_chroma_green")
    entry.filters.append(
        EntryFilter(
            id="chroma_key",
            properties={
                "mlt_service": "chroma",
                "kdenlive_id": "chroma",
                "key": "00:00:00.000=0x00ff00ff",
                "variance": "0.4",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "054-chroma-key-green.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 055 -- lumakey (white isolation)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_055_lumakey_white_isolation():
    """Key out luminance below threshold to isolate bright areas
    (e.g. white text on a darker background).  Scalar params --
    no keyframes."""
    project, entry = _project_with_clip("smoke_055_lumakey")
    entry.filters.append(
        EntryFilter(
            id="lumakey",
            properties={
                "mlt_service": "lumakey",
                "kdenlive_id": "lumakey",
                "threshold": "180",
                "slope": "60",
                "prelevel": "60",
                "postlevel": "215",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "055-lumakey-white-isolation.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 056 -- dynamictext (timecode overlay)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_056_dynamictext_timecode_overlay():
    """Render a timecode + frame counter overlay using MLT's
    ``dynamictext``.  ``argument`` carries the template with ``#tag#``
    placeholders Kdenlive substitutes per frame."""
    project, entry = _project_with_clip("smoke_056_dynamictext")
    entry.filters.append(
        EntryFilter(
            id="dynamictext",
            properties={
                "mlt_service": "dynamictext",
                "kdenlive_id": "dynamictext",
                "argument": "TC #timecode#  •  Frame #frame#",
                # Position: full-frame box, halign/valign decide where text sits
                "geometry": "00:00:00.000=0 0 1920 1080 1.000000",
                "family": "Segoe UI",
                "size": "64",
                "weight": "500",
                "style": "normal",
                "fgcolour": "00:00:00.000=0xffffffff",
                "bgcolour": "00:00:00.000=0x00000080",  # half-transparent black
                "olcolour": "00:00:00.000=0x00000000",
                "pad": "30",
                "halign": "right",
                "valign": "bottom",
                "outline": "0",
                "opacity": "1.0",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "056-dynamictext-timecode-overlay.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 057 -- timer (count-up clock overlay)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_057_timer_count_up_clock():
    """Render a count-up clock for the full clip duration.  Useful for
    workshop-style "X minutes elapsed" overlays."""
    project, entry = _project_with_clip("smoke_057_timer")
    entry.filters.append(
        EntryFilter(
            id="timer",
            properties={
                "mlt_service": "timer",
                "kdenlive_id": "timer",
                "format": "MM:SS.SSS",
                "start": "00:00:00.000",
                "duration": "100",      # show for 100 frames per cycle
                "offset": "00:00:00.000",
                "speed": "1",
                "direction": "up",
                "geometry": "0=0 0 1920 1080",
                "family": "Segoe UI",
                "size": "120",
                "weight": "600",
                "style": "normal",
                "fgcolour": "00:00:00.000=0xffffffff",
                "bgcolour": "00:00:00.000=0x00000064",
                "olcolour": "00:00:00.000=0x000000ff",
                "pad": "20",
                "halign": "centre",
                "valign": "middle",
                "outline": "1",
                "opacity": "1.0",
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "057-timer-count-up.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
