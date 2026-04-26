"""Smoke test batch 17.0: typewriter title animation.

Verified shape against the upstream KDE test-suite reference at
``tests/fixtures/kdenlive_references/typewriter_effect_upstream_kde.kdenlive``.

Kdenlive's typewriter title animation is encoded as a single attribute
on the ``<content>`` element of the ``kdenlivetitle`` xmldata payload:

    typewriter="<mode>;<speed>;<variation>;<seed>;<sigma>"

Where:
* ``mode`` -- 0 = disabled, 1 = enabled
* ``speed`` -- typing speed (frames per character)
* ``variation`` -- timing jitter (0 = perfectly metronomic)
* ``seed`` -- random seed for variation reproducibility
* ``sigma`` -- timing-distribution width

The upstream reference uses ``typewriter="1;8;1;0;0"`` -- enabled,
8 frames per char, ``variation=1`` (mild jitter), seed=0, sigma=0.

Smoke 053 emits a 5-second editable title with the typewriter animation
enabled.  Pending user verification in Kdenlive 25.x that the text
"types itself" in playback rather than appearing all at once.
"""
from __future__ import annotations

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


REPO_ROOT = Path(__file__).resolve().parents[2]
USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")


def _typewriter_kdenlivetitle_xmldata(
    text: str,
    *,
    width: int,
    height: int,
    length_frames: int,
    font_px: int = 96,
    font: str = "Segoe UI",
    color: str = "255,255,255,255",
    typewriter_mode: int = 1,
    typewriter_speed: int = 8,
    typewriter_variation: int = 1,
    typewriter_seed: int = 0,
    typewriter_sigma: int = 0,
) -> str:
    """Build a kdenlivetitle xmldata payload with the typewriter animation
    attribute on its content element.

    Verified attribute format: ``typewriter="<mode>;<speed>;<variation>;<seed>;<sigma>"``
    where mode=1 enables the animation."""
    out = max(0, length_frames - 1)
    box_w = int(width * 0.8)
    box_h = int(height * 0.2)
    pos_x = (width - box_w) // 2
    pos_y = (height - box_h) // 2
    typewriter_attr = (
        f"{typewriter_mode};{typewriter_speed};"
        f"{typewriter_variation};{typewriter_seed};{typewriter_sigma}"
    )
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
        f'typewriter="{typewriter_attr}">{text}</content>\n'
        f' </item>\n'
        f' <startviewport rect="0,0,{width},{height}"/>\n'
        f' <endviewport rect="0,0,{width},{height}"/>\n'
        f' <background color="0,0,0,0"/>\n'
        f'</kdenlivetitle>\n'
    )


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_053_typewriter_title_animation():
    """5-second editable title that types itself out at 8 frames per
    character with mild timing jitter."""
    fps = 29.97
    length_frames = int(5 * fps)
    width = 1920
    height = 1080
    label = "Hello, world!"

    project = KdenliveProject(
        version="7",
        title="smoke_053_typewriter_title",
        profile=ProjectProfile(width=width, height=height, fps=fps, colorspace="709"),
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

    xmldata = _typewriter_kdenlivetitle_xmldata(
        label,
        width=width,
        height=height,
        length_frames=length_frames,
        typewriter_mode=1,
        typewriter_speed=8,
        typewriter_variation=1,
        typewriter_seed=0,
        typewriter_sigma=0,
    )
    title_id = "title_typewriter"
    total_seconds = length_frames / fps
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    f = length_frames - int(int(total_seconds) * fps)
    duration_tc = f"{h:02d}:{m:02d}:{s:02d};{max(0, f):02d}"

    project.producers.append(
        Producer(
            id=title_id,
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
                "kdenlive:duration": duration_tc,
                "xmldata": xmldata,
            },
        )
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    pl.entries.append(
        PlaylistEntry(producer_id=title_id, in_point=0, out_point=length_frames - 1)
    )

    out_path = _output_dir() / "053-typewriter-title-animation.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    text = out_path.read_text(encoding="utf-8")
    # The typewriter attribute should reach the output xmldata (which the
    # serializer escapes into the <property name="xmldata"> child).
    assert "typewriter=" in text
    assert "1;8;1;0;0" in text
