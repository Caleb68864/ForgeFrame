"""Smoke test batch 6.0: image+qtblend transform, building up to parallax.

Builds on the verified image-producer primitive (smokes 012-014) by
attaching ``qtblend`` filters to playlist entries.  Reference for the
shape: ``tests/fixtures/kdenlive_references/image_transform_native.kdenlive``
(the user's hand-saved 04-image-transform.kdenlive).

Order:
- 015 -- image with a STATIC qtblend filter (one rect keyframe at frame 0,
  filling the canvas).  Verifies the filter is recognised when emitted
  inside the ``<entry>`` element.
- 016 -- image with TWO rect keyframes for a slow horizontal pan.
  Verifies the keyframe-string syntax works.
- 017 -- full parallax sequence: solid color background on V1, seven
  XKCD images on V2 each with a Ken Burns slow pan, an editable
  title at the start and end.

The ``qtblend`` transform's ``rect`` keyframe format is
``TIMECODE=x y w h opacity`` separated by ``;``.  TIMECODE is
``HH:MM:SS.fff`` (millisecond precision).  x/y/w/h are pixels in the
project canvas's coordinate space.
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
from workshop_video_brain.core.models.timeline import CreateTrack
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")
XKCD_DIR = Path("C:/Users/CalebBennett/Pictures/XKCD")


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


def _frames_to_timecode(frame: int, fps: float) -> str:
    """Convert a frame index to ``HH:MM:SS.fff`` timecode at *fps*."""
    seconds = frame / fps
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s_total = seconds - h * 3600 - m * 60
    s_int = int(s_total)
    ms = int(round((s_total - s_int) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s_int:02d}.{ms:03d}"


def _add_image_producer(
    project: KdenliveProject,
    *,
    producer_id: str,
    image_path: Path,
    length_frames: int,
    label: str,
) -> KdenliveProject:
    """Pre-register a Kdenlive 25 ``mlt_service=qimage`` producer.

    Includes the full property set the reference file (image_transform_native)
    carries: ttl, format, seekable, meta.media.progressive, file_size and
    a timecode-formatted length so Kdenlive accepts the producer at load.
    """
    new = project.model_copy(deep=True)
    resource = str(image_path).replace("\\", "/")
    fps = new.profile.fps or 25.0
    length_tc = _frames_to_timecode(length_frames, fps)
    try:
        file_size = image_path.stat().st_size
    except OSError:
        file_size = 0

    new.producers.append(
        Producer(
            id=producer_id,
            resource=resource,
            properties={
                "mlt_service": "qimage",
                "resource": resource,
                "length": length_tc,
                "eof": "pause",
                "ttl": "25",
                "aspect_ratio": "1",
                "meta.media.progressive": "1",
                "seekable": "1",
                "format": "1",
                "kdenlive:duration": length_tc,
                "kdenlive:clipname": label,
                **({"kdenlive:file_size": str(file_size)} if file_size else {}),
            },
        )
    )
    return new


def _add_color_producer(
    project: KdenliveProject,
    *,
    producer_id: str,
    color_hex: str,
    length_frames: int,
    label: str,
) -> KdenliveProject:
    new = project.model_copy(deep=True)
    new.producers.append(
        Producer(
            id=producer_id,
            resource=color_hex,
            properties={
                "mlt_service": "color",
                "resource": color_hex,
                "length": str(length_frames),
                "kdenlive:clipname": label,
            },
        )
    )
    return new


def _kdenlivetitle_xmldata(
    text: str, *, width: int, height: int, length_frames: int,
    font_px: int, font: str, color: str,
) -> str:
    out = max(0, length_frames - 1)
    box_w = int(width * 0.8)
    box_h = int(height * 0.2)
    pos_x = (width - box_w) // 2
    pos_y = (height - box_h) // 2
    return (
        f'<kdenlivetitle LC_NUMERIC="C" duration="{length_frames}" '
        f'height="{height}" out="{out}" width="{width}">\n'
        f' <item type="QGraphicsTextItem" z-index="0">\n'
        f'  <position x="{pos_x}" y="{pos_y}">\n'
        f'   <transform>1,0,0,0,1,0,0,0,1</transform>\n'
        f'  </position>\n'
        f'  <content alignment="4" box-height="{box_h}" box-width="{box_w}" '
        f'font="{font}" font-color="{color}" font-italic="0" '
        f'font-outline="0" font-outline-color="0,0,0,255" '
        f'font-pixel-size="{font_px}" font-underline="0" font-weight="400" '
        f'letter-spacing="0" shadow="0;#64000000;3;3;3" tab-width="80" '
        f'typewriter="0;2;1;0;0">{text}</content>\n'
        f' </item>\n'
        f' <startviewport rect="0,0,{width},{height}"/>\n'
        f' <endviewport rect="0,0,{width},{height}"/>\n'
        f' <background color="0,0,0,0"/>\n'
        f'</kdenlivetitle>\n'
    )


def _duration_timecode_with_frames(length_frames: int, fps: float) -> str:
    """``HH:MM:SS;FF`` semicolon-style timecode used by ``kdenlive:duration``."""
    total_seconds = length_frames / fps
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    frames = length_frames - int(int(total_seconds) * fps)
    return f"{h:02d}:{m:02d}:{s:02d};{max(0, frames):02d}"


def _add_kdenlivetitle(
    project: KdenliveProject, producer_id: str, label: str,
    length_frames: int, *, font_px: int = 84, color: str = "255,255,255,255",
    font: str = "Segoe UI",
) -> KdenliveProject:
    new = project.model_copy(deep=True)
    width, height = new.profile.width, new.profile.height
    fps = new.profile.fps or 25.0
    xmldata = _kdenlivetitle_xmldata(
        label, width=width, height=height, length_frames=length_frames,
        font_px=font_px, font=font, color=color,
    )
    new.producers.append(
        Producer(
            id=producer_id,
            resource="",
            properties={
                "mlt_service": "kdenlivetitle",
                "resource": "",
                "length": str(length_frames),
                "eof": "pause",
                "aspect_ratio": "1",
                "seekable": "1",
                "meta.media.progressive": "1",
                "meta.media.width": str(width),
                "meta.media.height": str(height),
                "force_reload": "0",
                "kdenlive:clipname": label,
                "kdenlive:duration": _duration_timecode_with_frames(length_frames, fps),
                "xmldata": xmldata,
            },
        )
    )
    return new


def _place_clip(
    project: KdenliveProject, *,
    producer_id: str, track_id: str, in_point: int, out_point: int,
    blank_before: int = 0,
    filters: list[EntryFilter] | None = None,
) -> KdenliveProject:
    new = project.model_copy(deep=True)
    pl = next(p for p in new.playlists if p.id == track_id)
    if blank_before > 0:
        pl.entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=blank_before - 1))
    pl.entries.append(
        PlaylistEntry(
            producer_id=producer_id,
            in_point=in_point,
            out_point=out_point,
            filters=filters or [],
        )
    )
    return new


def _qtblend_filter(
    *,
    rect_keyframes: list[tuple[int, str]],
    rotation_keyframes: list[tuple[int, str]] | None = None,
    fps: float,
) -> EntryFilter:
    """Build a Kdenlive ``qtblend`` transform filter.

    Args:
        rect_keyframes: ``(frame, "x y w h opacity")`` tuples.  Opacity in
            ``0.0``-``1.0`` with six decimals is what Kdenlive emits.
        rotation_keyframes: optional ``(frame, "<degrees>")`` tuples.
            Defaults to ``0`` degrees at every rect keyframe time.
        fps: project frame rate, used to convert frames to timecodes.
    """
    rect_str = ";".join(
        f"{_frames_to_timecode(frame, fps)}={value}"
        for frame, value in rect_keyframes
    )
    if rotation_keyframes is None:
        rotation_keyframes = [(frame, "0") for frame, _ in rect_keyframes]
    rotation_str = ";".join(
        f"{_frames_to_timecode(frame, fps)}={value}"
        for frame, value in rotation_keyframes
    )
    return EntryFilter(
        properties={
            "rotate_center": "1",
            "mlt_service": "qtblend",
            "kdenlive_id": "qtblend",
            "compositing": "0",
            "distort": "0",
            "rect": rect_str,
            "rotation": rotation_str,
            "kdenlive:collapsed": "0",
        }
    )


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _xkcd(name: str) -> Path | None:
    p = XKCD_DIR / name
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# 015 -- image with a static qtblend filter (single rect keyframe)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_015_image_with_static_qtblend():
    """Image filling the canvas with a static qtblend rect (no movement).
    Tests that an EntryFilter inside <entry> renders correctly."""
    img = _xkcd("compiling.png")
    if img is None:
        pytest.skip("compiling.png missing")

    fps = 29.97
    length = int(4 * fps)
    project = _build_initial_project("smoke_015_static_qtblend", fps=fps)
    project = _add_image_producer(
        project,
        producer_id="img_compiling",
        image_path=img,
        length_frames=length,
        label="Compiling",
    )
    f = _qtblend_filter(
        rect_keyframes=[(0, "0 0 1920 1080 1.000000")],
        fps=fps,
    )
    project = _place_clip(
        project,
        producer_id="img_compiling",
        track_id="playlist_video",
        in_point=0,
        out_point=length - 1,
        filters=[f],
    )
    out_path = _output_dir() / "015-image-static-qtblend.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 016 -- image with a 2-keyframe qtblend pan (parallax)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_016_image_with_qtblend_parallax():
    """Slow horizontal pan: rect drifts from x=0 to x=-100 over the clip
    duration, with the image scaled up by 5%.  This is the simplest
    Ken Burns / parallax pattern."""
    img = _xkcd("dependency.png")
    if img is None:
        pytest.skip("dependency.png missing")

    fps = 29.97
    length = int(5 * fps)  # 5-second pan
    project = _build_initial_project("smoke_016_qtblend_parallax", fps=fps)
    project = _add_image_producer(
        project,
        producer_id="img_dependency",
        image_path=img,
        length_frames=length,
        label="Dependency Hell",
    )
    # Image scaled up 5% (2016x1134, off-canvas by 96 horizontally).
    # Drift x from 0 to -96 over the duration; height stays at 1134, y at -27.
    f = _qtblend_filter(
        rect_keyframes=[
            (0,           "0 -27 2016 1134 1.000000"),
            (length - 1,  "-96 -27 2016 1134 1.000000"),
        ],
        fps=fps,
    )
    project = _place_clip(
        project,
        producer_id="img_dependency",
        track_id="playlist_video",
        in_point=0,
        out_point=length - 1,
        filters=[f],
    )
    out_path = _output_dir() / "016-image-qtblend-parallax.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 017 -- full parallax sequence: 7 XKCD images + color bg + titles
# ---------------------------------------------------------------------------


# Image dimensions for the XKCD fixtures (read from the reference file).
_XKCD_IMAGES: list[tuple[str, str, int, int]] = [
    ("img_compiling",  "compiling.png",  413, 360),
    ("img_dependency", "dependency.png", 385, 489),
    ("img_iso",        "iso_8601-1.png", 392, 457),
    ("img_tags",       "tags-1.png",     451,  57),
    ("img_tar",        "tar-1.png",      713, 229),
    ("img_workflow",   "workflow-1.png", 278, 386),
    ("img_x11",        "x11-1.png",      319, 261),
]


def _kenburns_rect(
    canvas_w: int,
    canvas_h: int,
    *,
    start_scale: float,
    end_scale: float,
    x_drift: int = 0,
    y_drift: int = 0,
) -> tuple[str, str]:
    """Return ``(start_rect, end_rect)`` for a Ken Burns zoom + drift.

    The image is centered at each scale and then offset by ``x_drift`` /
    ``y_drift`` over the clip's duration.  ``start_scale != end_scale``
    produces a visible zoom; equal scales produce a pure pan.
    """
    def _rect(scale: float, dx: int, dy: int) -> str:
        w = int(canvas_w * scale)
        h = int(canvas_h * scale)
        x = (canvas_w - w) // 2 + dx
        y = (canvas_h - h) // 2 + dy
        return f"{x} {y} {w} {h} 1.000000"

    return _rect(start_scale, 0, 0), _rect(end_scale, x_drift, y_drift)


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_017_xkcd_parallax_sequence():
    """The full ask: solid color background on V1, 7 XKCD images on V2
    sequentially with Ken Burns parallax pans, intro+outro titles on V3."""
    available = [
        (pid, p, w, h)
        for pid, name, w, h in _XKCD_IMAGES
        for p in [_xkcd(name)]
        if p is not None
    ]
    if len(available) < 3:
        pytest.skip("Need at least 3 XKCD images")

    fps = 29.97
    per_image_seconds = 4.0
    per_image_frames = int(per_image_seconds * fps)
    intro_frames = int(2 * fps)
    outro_frames = int(2 * fps)
    total_frames = intro_frames + per_image_frames * len(available) + outro_frames

    project = _build_initial_project("smoke_017_xkcd_parallax", fps=fps)
    # V2 (image overlay) and V3 (title overlay)
    project = patch_project(project, [CreateTrack(track_type="video", name="V2 images")])
    project = patch_project(project, [CreateTrack(track_type="video", name="V3 titles")])

    canvas_w = project.profile.width
    canvas_h = project.profile.height

    # V1 -- solid color background spanning the whole timeline.
    project = _add_color_producer(
        project,
        producer_id="bg_navy",
        color_hex="#0b1226",
        length_frames=total_frames,
        label="Navy Background",
    )
    project = _place_clip(
        project,
        producer_id="bg_navy",
        track_id="playlist_video",
        in_point=0,
        out_point=total_frames - 1,
    )

    # V3 -- intro title (at start), outro title (at end).
    project = _add_kdenlivetitle(
        project,
        producer_id="title_intro",
        label="XKCD Selection",
        length_frames=intro_frames,
        font_px=120,
    )
    project = _add_kdenlivetitle(
        project,
        producer_id="title_outro",
        label="Thanks for watching",
        length_frames=outro_frames,
        font_px=96,
    )
    project = _place_clip(
        project,
        producer_id="title_intro",
        track_id="playlist_video_2",
        in_point=0,
        out_point=intro_frames - 1,
    )
    # Outro at the end with a leading blank.
    blank_until_outro = intro_frames + per_image_frames * len(available)
    project = _place_clip(
        project,
        producer_id="title_outro",
        track_id="playlist_video_2",
        in_point=0,
        out_point=outro_frames - 1,
        blank_before=blank_until_outro,
    )

    # V2 -- 7 images sequentially after the intro, each with a Ken Burns pan.
    # Alternate between dramatic zoom-in (scale grows over time, drifts toward
    # one corner) and zoom-out (scale shrinks, drifts toward the other) so
    # consecutive images don't feel monotonous.
    moves = [
        # (start_scale, end_scale, x_drift, y_drift)
        (1.10, 1.45,  240,   0),    # zoom-in pan right
        (1.45, 1.10, -240,   0),    # zoom-out pan left
        (1.20, 1.50,    0, -120),   # zoom-in toward top
        (1.50, 1.20,    0,  120),   # zoom-out toward bottom
        (1.10, 1.40,  200,  100),   # zoom-in toward bottom-right
        (1.40, 1.10, -200, -100),   # zoom-out toward top-left
        (1.15, 1.45,  -150, 80),    # zoom-in toward bottom-left
    ]
    for idx, (pid, p, w, h) in enumerate(available):
        # Each image starts after the intro + previous images' duration
        offset = intro_frames + idx * per_image_frames
        project = _add_image_producer(
            project,
            producer_id=pid,
            image_path=p,
            length_frames=per_image_frames,
            label=p.stem,
        )
        start_scale, end_scale, x_drift, y_drift = moves[idx % len(moves)]
        rect_start, rect_end = _kenburns_rect(
            canvas_w, canvas_h,
            start_scale=start_scale,
            end_scale=end_scale,
            x_drift=x_drift,
            y_drift=y_drift,
        )
        # Keyframe timestamps are LOCAL to the entry (relative to its in_point),
        # NOT absolute sequence frames.  Putting absolute sequence positions
        # here causes keyframes after the first clip to fall beyond their
        # entry's local duration, which Kdenlive then clamps to a single
        # effective keyframe -- and the parallax stops moving.
        f = _qtblend_filter(
            rect_keyframes=[
                (0, rect_start),
                (per_image_frames - 1, rect_end),
            ],
            fps=fps,
        )
        project = _place_clip(
            project,
            producer_id=pid,
            track_id="playlist_video_1",
            in_point=0,
            out_point=per_image_frames - 1,
            blank_before=offset if idx == 0 else (per_image_frames - per_image_frames),
            filters=[f],
        )

    out_path = _output_dir() / "017-xkcd-parallax-sequence.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
