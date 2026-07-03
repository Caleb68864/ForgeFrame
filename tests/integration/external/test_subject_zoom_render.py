"""External render-proof for motion tracking + subject auto-zoom (plan §5).

Non-self-referential oracle test: it shells out to real ``ffmpeg`` (deterministic
fixture) and real ``melt`` (tracking analysis + render), and asserts truth about
decoded pixels -- not that our parser and serializer agree.

Fixture: a textured 48x48 ``testsrc2`` patch moving left->right at a *known*
constant velocity on a plain grey background (CSRT needs interior texture; a
solid square tracks poorly -- established in the §5 spike). Known path::

    subject top-left x(frame) = 20 + (60 / fps) * frame     (y == 96, const)

Two proofs:

* ``test_tracking_follows_known_path`` -- run the real MLT ``opencv.tracker``
  through ``subject_track`` and assert the tracked top-left follows the known
  path within tolerance; the max deviation is reported.
* ``test_subject_zoom_centres_on_subject`` -- apply ``subject_zoom`` with the
  tracked data, render a frame with real ``melt``, and assert the frame centre
  now shows the textured subject (colourful) while the *un-zoomed* render shows
  plain grey background there -- i.e. the zoom followed the subject to centre.

This module adds NO changes to ``_oracle``/``builders`` internals.
"""
from __future__ import annotations

import json
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
from workshop_video_brain.edit_mcp.server.bundles import motion_track as bundle

from ._oracle import _open_rgb, render_frame

pytestmark = pytest.mark.external

# Fixture geometry (must stay in lock-step with the ffmpeg command below).
WIDTH, HEIGHT, FPS, FRAMES = 320, 240, 25.0, 50
PATCH = 48
PATCH_Y = 96
SEED_X, VELOCITY = 20, 60.0  # x = SEED_X + VELOCITY * t(seconds)


def _known_topleft_x(frame: int) -> float:
    """Ground-truth subject top-left x at *frame* (from the ffmpeg expression)."""
    return SEED_X + VELOCITY * (frame / FPS)


@pytest.fixture(scope="module")
def moving_patch_clip(tmp_path_factory, ffmpeg_bin) -> Path:
    """A deterministic clip: a textured patch tracking a known linear path."""
    out = tmp_path_factory.mktemp("mt_fixture") / "moving_patch.mp4"
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", f"color=c=gray:s={WIDTH}x{HEIGHT}:r={int(FPS)}:d=2",
        "-f", "lavfi", "-i", f"testsrc2=s={PATCH}x{PATCH}:r={int(FPS)}:d=2",
        "-filter_complex",
        f"[0][1]overlay=x='{SEED_X}+{int(VELOCITY*2)}*t/2':y={PATCH_Y}",
        "-frames:v", str(FRAMES),
        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not out.exists():
        raise RuntimeError(
            f"fixture generation failed: rc={proc.returncode}\n{proc.stderr[-800:]}"
        )
    return out


def _build_workspace(tmp_path: Path, clip: Path) -> tuple[Path, str, KdenliveProject]:
    """A minimal workspace: an mp4-backed single-clip project on one track."""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    # Real workspace layout so the serializer's pre-write snapshot lands here
    # (not the filesystem root) -- mirrors project_create_working_copy output.
    (ws / "projects" / "working_copies").mkdir(parents=True, exist_ok=True)
    prod = Producer(
        id="producer_0",
        resource=str(clip),
        properties={
            "resource": str(clip),
            "mlt_service": "avformat",
            "length": str(FRAMES + 10),
        },
    )
    proj = KdenliveProject(
        version="7",
        title="mt",
        profile=ProjectProfile(width=WIDTH, height=HEIGHT, fps=FPS, colorspace="709"),
    )
    proj.producers = [prod]
    proj.tracks = [
        Track(id="playlist_video", track_type="video", name="Video"),
        Track(id="playlist_audio", track_type="audio", name="Audio"),
    ]
    entry = PlaylistEntry(producer_id="producer_0", in_point=0, out_point=FRAMES - 1)
    proj.playlists = [
        Playlist(id="playlist_video", entries=[entry.model_copy(deep=True)]),
        Playlist(id="playlist_audio", entries=[entry.model_copy(deep=True)]),
    ]
    proj.tractor = {"id": "tractor0", "in": "0", "out": str(FRAMES - 1)}
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    project_file = "project.kdenlive"
    serialize_project(proj, ws / project_file)
    return ws, project_file, proj


def _center_channel_spread(png: Path, half: int = 40) -> float:
    """Max spread between the R/G/B channel means over the frame's centre box.

    Grey background -> ~0 (all channels equal); a colourful textured subject ->
    a large spread. A robust, distro-independent 'is the centre the subject?'.
    """
    im = _open_rgb(png)
    w, h = im.size
    cx, cy = w // 2, h // 2
    box = im.crop((cx - half, cy - half, cx + half, cy + half))
    px = list(box.getdata())
    n = len(px)
    r = sum(p[0] for p in px) / n
    g = sum(p[1] for p in px) / n
    b = sum(p[2] for p in px) / n
    return max(r, g, b) - min(r, g, b)


# ---------------------------------------------------------------------------
# Proof 1: tracking follows the known path
# ---------------------------------------------------------------------------

def test_tracking_accuracy(tmp_path, moving_patch_clip, melt_bin):
    """Real MLT opencv.tracker output follows the known linear path."""
    from .conftest import melt_has_service

    if not melt_has_service(melt_bin, "filters", "opencv.tracker"):
        pytest.skip("melt built without opencv.tracker -- motion tracking unavailable")

    ws, project_file, _ = _build_workspace(tmp_path, moving_patch_clip)
    res = bundle.subject_track(
        workspace_path=str(ws),
        project_file=project_file,
        track=0,
        clip_index=0,
        rect=f"{SEED_X} {PATCH_Y} {PATCH} {PATCH}",
        algorithm="csrt",
    )
    assert res["status"] == "success", res
    data = json.loads(Path(res["data"]["track_data"]).read_text())
    kfs = data["keyframes"]
    assert len(kfs) >= 3, "expected multiple tracked keyframes"

    max_dev = 0.0
    for k in kfs:
        frame = k["frame"]
        x = k["rect"][0]
        y = k["rect"][1]
        dev_x = abs(x - _known_topleft_x(frame))
        dev_y = abs(y - PATCH_Y)
        max_dev = max(max_dev, dev_x, dev_y)

    # CSRT on a clean textured patch tracks tightly; allow a generous margin
    # (~15% of the patch) for sub-pixel drift / codec differences.
    print(f"[tracking] frames={len(kfs)} engine={data['engine']} "
          f"max_deviation_px={max_dev:.2f}")
    assert max_dev < 8.0, f"tracked path deviates {max_dev:.2f}px from known path"


def test_opencv_fallback_tracks_known_path(moving_patch_clip):
    """The OpenCV fallback engine (opencv-contrib) tracks the same path.

    Skipped when ``cv2`` is absent -- the ``motion-track`` extra is optional and
    the default engine is melt. Proves the documented fallback is real.
    """
    import importlib.util

    if importlib.util.find_spec("cv2") is None:
        pytest.skip("opencv not installed (motion-track extra) -- fallback test skipped")

    from workshop_video_brain.edit_mcp.pipelines import motion_track as mt

    kfs = mt.run_opencv_tracker(
        moving_patch_clip, (SEED_X, PATCH_Y, PATCH, PATCH), "CSRT",
        start_frame=0, end_frame=FRAMES - 1,
    )
    assert len(kfs) >= 3
    max_dev = max(
        max(abs(x - _known_topleft_x(f)), abs(y - PATCH_Y))
        for f, (x, y, _w, _h) in kfs
    )
    print(f"[opencv-fallback] frames={len(kfs)} max_deviation_px={max_dev:.2f}")
    assert max_dev < 8.0, f"opencv path deviates {max_dev:.2f}px from known path"


# ---------------------------------------------------------------------------
# Proof 2: subject_zoom centres the frame on the subject
# ---------------------------------------------------------------------------

def test_subject_zoom_centres_on_subject(tmp_path, moving_patch_clip, melt_bin):
    """After subject_zoom, the frame centre shows the subject; before, grey."""
    from .conftest import melt_has_service

    if not melt_has_service(melt_bin, "filters", "opencv.tracker"):
        pytest.skip("melt built without opencv.tracker -- motion tracking unavailable")

    ws, project_file, _ = _build_workspace(tmp_path, moving_patch_clip)

    # Baseline: the un-zoomed render's centre is plain grey background.
    base_png = render_frame(
        ws / project_file, 25, tmp_path, melt_bin=melt_bin, name="base_f25.png"
    )
    base_spread = _center_channel_spread(base_png)

    # Track, then apply the follow-zoom.
    track_res = bundle.subject_track(
        workspace_path=str(ws), project_file=project_file,
        track=0, clip_index=0,
        rect=f"{SEED_X} {PATCH_Y} {PATCH} {PATCH}", algorithm="csrt",
    )
    assert track_res["status"] == "success", track_res

    zoom_res = bundle.subject_zoom(
        workspace_path=str(ws), project_file=project_file,
        track=0, clip_index=0,
        track_data=track_res["data"]["track_data"],
        fill=0.5, smoothing=5, ease="cubic",
    )
    assert zoom_res["status"] == "success", zoom_res

    zoom_png = render_frame(
        ws / project_file, 25, tmp_path, melt_bin=melt_bin, name="zoom_f25.png"
    )
    zoom_spread = _center_channel_spread(zoom_png)

    print(f"[zoom] base_center_spread={base_spread:.1f} "
          f"zoom_center_spread={zoom_spread:.1f}")

    # Un-zoomed centre is near-grey (channels ~equal); zoomed centre carries the
    # colourful subject the follow-zoom brought to the middle of the frame.
    assert base_spread < 12.0, (
        f"baseline frame centre unexpectedly colourful ({base_spread:.1f}) -- "
        "fixture background is not plain grey"
    )
    # base ~5 (grey), zoom ~19 (colourful subject) in practice: require an
    # unmistakable jump so a no-op transform can never pass.
    assert zoom_spread > 12.0 and zoom_spread > base_spread + 8.0, (
        f"subject_zoom did not bring the subject to centre "
        f"(base={base_spread:.1f}, zoom={zoom_spread:.1f})"
    )
