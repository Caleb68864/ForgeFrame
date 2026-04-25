"""Smoke test batch 5.0: incremental verification of new primitives.

Before attempting a full parallax sequence (image clips + animated affine
filter + color background + titles), test the building blocks one at a
time so we know exactly which primitive fails when something breaks.

Order:
- 012-image-producer-basic: a single image on V1 with no animation.
  Tests ``mlt_service=qimage`` as a producer and verifies Kdenlive
  loads the image in the bin and renders it on the timeline.
- 013-image-with-color-bg: same image on V2 with a solid-color clip on
  V1 underneath.  Tests stacking a non-chain producer on V1 plus image
  on V2 (the parallax base layout, but without animation).
- 014-multi-images-back-to-back: 3 images on V1 in sequence (no
  animation, hard cuts).  Tests that several image producers can
  coexist in the bin.

If 012/013/014 all open cleanly, we know the image primitive works and
we can add the affine-keyframe layer on top in a follow-up smoke.
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


def _add_image_producer(
    project: KdenliveProject,
    *,
    producer_id: str,
    image_path: Path,
    length_frames: int,
    label: str,
) -> KdenliveProject:
    """Pre-register an ``mlt_service=qimage`` producer for a still image.

    Image producers are emitted as ``<producer>`` (not ``<chain>`` --
    only avformat media gets the chain twin pattern).  The serializer's
    ``_clip_type`` returns 5 (Image) for ``qimage`` / ``pixbuf`` services.
    """
    new = project.model_copy(deep=True)
    resource = str(image_path).replace("\\", "/")
    new.producers.append(
        Producer(
            id=producer_id,
            resource=resource,
            properties={
                "mlt_service": "qimage",
                "resource": resource,
                "length": str(length_frames),
                "eof": "pause",
                "aspect_ratio": "1",
                "kdenlive:clipname": label,
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
    """Pre-register a ``mlt_service=color`` solid-color clip."""
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


def _place_clip(
    project: KdenliveProject,
    *,
    producer_id: str,
    track_id: str,
    in_point: int,
    out_point: int,
    blank_before: int = 0,
) -> KdenliveProject:
    """Append a playlist entry referencing a pre-registered producer.

    Skips the patcher's ``AddClip`` because ``AddClip`` rewrites producer
    properties to ``avformat-novalidate`` -- which would clobber our
    ``qimage`` / ``color`` producer settings.
    """
    new = project.model_copy(deep=True)
    pl = next(p for p in new.playlists if p.id == track_id)
    if blank_before > 0:
        pl.entries.append(
            PlaylistEntry(producer_id="", in_point=0, out_point=blank_before - 1)
        )
    pl.entries.append(
        PlaylistEntry(producer_id=producer_id, in_point=in_point, out_point=out_point)
    )
    return new


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _xkcd(name: str) -> Path | None:
    p = XKCD_DIR / name
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# 012 -- image producer (single image on V1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_012_image_producer_basic():
    """Just one PNG on V1 for 4 seconds.  No animation, no background."""
    img = _xkcd("compiling.png")
    if img is None:
        pytest.skip(f"Image not found: {XKCD_DIR}/compiling.png")

    fps = 29.97
    length = int(4 * fps)
    project = _build_initial_project("smoke_012_image_basic", fps=fps)
    project = _add_image_producer(
        project,
        producer_id="img_compiling",
        image_path=img,
        length_frames=length,
        label="Compiling",
    )
    project = _place_clip(
        project,
        producer_id="img_compiling",
        track_id="playlist_video",
        in_point=0,
        out_point=length - 1,
    )
    out_path = _output_dir() / "012-image-producer-basic.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 013 -- image with color background (V1 = color, V2 = image)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_013_image_with_color_bg():
    """Color background on V1 plus an image on V2.  No animation.
    The image's natural size is preserved; it sits on top of the color
    background through the auto-emitted qtblend per-track composition."""
    img = _xkcd("dependency.png")
    if img is None:
        pytest.skip("dependency.png missing")

    fps = 29.97
    length = int(4 * fps)
    project = _build_initial_project("smoke_013_image_color_bg", fps=fps)
    # Add a second video track for the image overlay.
    from workshop_video_brain.core.models.timeline import CreateTrack
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    project = patch_project(project, [CreateTrack(track_type="video", name="V2")])

    project = _add_color_producer(
        project,
        producer_id="bg_navy",
        color_hex="#1a1a2e",
        length_frames=length,
        label="Navy Background",
    )
    project = _add_image_producer(
        project,
        producer_id="img_dependency",
        image_path=img,
        length_frames=length,
        label="Dependency",
    )
    # Color background on V1
    project = _place_clip(
        project,
        producer_id="bg_navy",
        track_id="playlist_video",
        in_point=0,
        out_point=length - 1,
    )
    # Image on V2 (the new track CreateTrack added)
    project = _place_clip(
        project,
        producer_id="img_dependency",
        track_id="playlist_video_1",
        in_point=0,
        out_point=length - 1,
    )
    out_path = _output_dir() / "013-image-with-color-bg.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 014 -- three images back to back on V1 (no animation)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_014_multi_images_back_to_back():
    """Three images, hard-cut between, 2.5 seconds each.  Tests several
    qimage producers coexisting in the bin and as sequential timeline
    entries on the same track."""
    fps = 29.97
    length = int(2.5 * fps)
    project = _build_initial_project("smoke_014_multi_images", fps=fps)

    images = [
        ("img_compiling",  "compiling.png",  "Compiling"),
        ("img_dependency", "dependency.png", "Dependency Hell"),
        ("img_workflow",   "workflow-1.png", "Workflow"),
    ]
    available: list[tuple[str, Path, str]] = []
    for pid, fname, label in images:
        p = _xkcd(fname)
        if p is None:
            continue
        available.append((pid, p, label))
    if len(available) < 2:
        pytest.skip("Need at least 2 XKCD images")

    for pid, p, label in available:
        project = _add_image_producer(
            project,
            producer_id=pid,
            image_path=p,
            length_frames=length,
            label=label,
        )
        project = _place_clip(
            project,
            producer_id=pid,
            track_id="playlist_video",
            in_point=0,
            out_point=length - 1,
        )

    out_path = _output_dir() / "014-multi-images-back-to-back.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
