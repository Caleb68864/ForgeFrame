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
  scalar tolerance.  Layered over a magenta colour generator on V1
  so transparent regions show as bright magenta.
* **055 lumakey** -- ``mlt_service=lumakey``, key by luminance.  Scalar
  ``threshold``/``slope``/``prelevel``/``postlevel``.  Layered over
  a cyan colour generator on V1 so transparent regions show as cyan.
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
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip, CreateTrack
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


def _build_keying_project(
    title: str,
    *,
    fps: float,
    duration: int,
    bg_color_resource: str,
    foreground_clip: Path,
    foreground_producer_id: str = "fg_clip",
) -> tuple[KdenliveProject, PlaylistEntry]:
    """Build a project with a colour-generator background on V1 and a
    real video clip on V2 (with the foreground entry returned so the
    caller can attach a chroma/luma key filter to it).

    The colour generator uses ``mlt_service=color`` with a named or
    hex resource (e.g. ``"magenta"``, ``"#ff00ff"``).  The clip on V2
    composites OVER V1, so when keying makes pixels transparent the
    background colour bleeds through -- making the keying effect
    visible even on source clips that don't naturally have green/blue
    backgrounds."""
    project = _build_initial_project(title, fps=fps)

    # ---- V1: colour-generator background --------------------------
    bg_producer_id = "bg_color"
    project.producers.append(
        Producer(
            id=bg_producer_id,
            resource=bg_color_resource,
            properties={
                "length": str(duration),
                "eof": "pause",
                "resource": bg_color_resource,
                "aspect_ratio": "1",
                "mlt_service": "color",
                "mlt_image_format": "rgba",
            },
        )
    )
    pl_v1 = next(p for p in project.playlists if p.id == "playlist_video")
    pl_v1.entries.append(
        PlaylistEntry(
            producer_id=bg_producer_id,
            in_point=0,
            out_point=duration - 1,
        )
    )

    # ---- V2: foreground clip (where the key filter goes) ----------
    project = patch_project(project, [CreateTrack(track_type="video", name="V2")])
    # CreateTrack appended the new track; its playlist id is
    # ``playlist_video_1`` (the first auto-generated suffix).
    project = _add_clip(
        project,
        producer_id=foreground_producer_id,
        track_id="playlist_video_1",
        in_point=0,
        out_point=duration - 1,
        source_path=str(foreground_clip),
    )
    pl_v2 = next(p for p in project.playlists if p.id == "playlist_video_1")
    return project, pl_v2.entries[0]


# ---------------------------------------------------------------------------
# 054 -- native chroma key (green-screen)
# ---------------------------------------------------------------------------


GREENSCREEN_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "greenscreen_reporter_720.mp4"


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_054_chroma_key_green_over_magenta():
    """Chroma key out pure green from the downloaded green-screen
    reporter clip; layered over a bright magenta colour generator on
    V1 so the keyed-out regions show as magenta.

    The Mixkit clip is a reporter standing in front of a green
    chroma-key background -- exactly what this filter is designed
    for.  After keying:

    * The reporter (subject) plays normally on V2
    * The green background becomes transparent
    * Magenta from V1 shows through where the green used to be

    If the entire frame is magenta, the key took out everything
    (variance too high).  If the green background still shows through
    the reporter unchanged, the key didn't take effect."""
    if not GREENSCREEN_CLIP.exists():
        pytest.skip(f"Green-screen clip missing: {GREENSCREEN_CLIP}")

    fps = 29.97
    duration = int(5 * fps)  # use first 5 seconds of the 20s clip

    project, fg_entry = _build_keying_project(
        "smoke_054_chroma_green_over_magenta",
        fps=fps,
        duration=duration,
        bg_color_resource="magenta",
        foreground_clip=GREENSCREEN_CLIP,
    )
    fg_entry.filters.append(
        EntryFilter(
            id="chroma_key",
            properties={
                "mlt_service": "chroma",
                "kdenlive_id": "chroma",
                "key": "00:00:00.000=0x00ff00ff",
                "variance": "0.25",  # tighter tolerance for cleaner key
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
def test_055_lumakey_dark_areas_over_cyan():
    """Key out DARK pixels to keep only bright regions; layer over
    a cyan colour generator on V1 so transparent regions show as
    cyan.

    Threshold=80 means pixels with luminance below 80 (dark areas
    like shadows, dark fabrics, dark backgrounds) become transparent.
    The lumakey is more useful for "isolate the bright subject from
    a dark background" workflows than for general keying.

    Verify by playing back: cyan should bleed through the dark areas
    of the source clip.  If no cyan is visible, threshold is too low
    and the key is a no-op.  If everything is cyan, threshold is too
    high."""
    if not GREENSCREEN_CLIP.exists():
        pytest.skip(f"Test clip missing: {GREENSCREEN_CLIP}")

    fps = 29.97
    duration = int(5 * fps)

    project, fg_entry = _build_keying_project(
        "smoke_055_lumakey_dark_over_cyan",
        fps=fps,
        duration=duration,
        bg_color_resource="cyan",
        foreground_clip=GREENSCREEN_CLIP,
    )
    fg_entry.filters.append(
        EntryFilter(
            id="lumakey",
            properties={
                "mlt_service": "lumakey",
                "kdenlive_id": "lumakey",
                "threshold": "80",       # keep pixels brighter than 80
                "slope": "40",           # softer transition over 40 levels
                "prelevel": "0",
                "postlevel": "255",
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
