"""External render proofs for the clip-placement engine (pixel-positional).

These tests shell out to real ``melt`` + ``ffprobe`` (skipped when absent) and
prove the placement is correct where it matters most -- the actual pixels at
specific times:

* **overwrite** -- a blue clip placed at t=2.0s for 1.0s on the upper track over a
  red base: frame at 1.9s is red, 2.5s is blue, 3.1s is red.
* **insert** -- content after T shifts right by the clip length (a colour that was
  at frame F is now at F+len) and the total rendered duration grows.
* **cross-track move** -- the clip's old position reveals the lower track; its new
  position shows the moved clip.
* **match-length** -- the placed B-roll spans exactly the reference clip's length
  (frame + report checks).

Plus a melt-accept smoke for every mode.

Projects are built inline from MLT ``color:`` producers (no media files, distro
-independent). ``builders``/``_oracle`` internals are used read-only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Guide,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import MoveClipToTrack, PlaceClip
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import melt_accepts, mean_color, probe, render_frame, render_video

pytestmark = pytest.mark.external

FPS = 25.0
W, H = 320, 180

RED = builders.RED      # 0xff0000ff
BLUE = builders.BLUE    # 0x0000ffff
GREEN = builders.GREEN  # 0x00ff00ff
WHITE = builders.WHITE  # 0xffffffff


def _prod(pid: str, resource: str, length: int = 400) -> Producer:
    return Producer(
        id=pid,
        resource=resource,
        properties={"resource": resource, "mlt_service": "color", "length": str(length)},
    )


def _dominant(png) -> str:
    """Classify a rendered frame's dominant primary as 'red'/'blue'/'green'/'white'."""
    r, g, b = mean_color(png)
    if r > 160 and g > 160 and b > 160:
        return "white"
    if r > 120 and g < 90 and b < 90:
        return "red"
    if b > 120 and r < 90 and g < 90:
        return "blue"
    if g > 120 and r < 90 and b < 90:
        return "green"
    return f"other(r={r:.0f},g={g:.0f},b={b:.0f})"


# ---------------------------------------------------------------------------
# overwrite
# ---------------------------------------------------------------------------

def _two_track_base() -> KdenliveProject:
    """Bottom video track = red (160 frames), empty upper video track + audio."""
    p = KdenliveProject(title="overwrite", profile=ProjectProfile(width=W, height=H, fps=FPS))
    p.producers = [_prod("red", RED), _prod("blue", BLUE)]
    p.tracks = [
        Track(id="vbottom", track_type="video"),
        Track(id="vtop", track_type="video"),
        Track(id="a1", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="vbottom", entries=[PlaylistEntry(producer_id="red", in_point=0, out_point=159)]),
        Playlist(id="vtop", entries=[]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "159"}
    return p


def test_overwrite_places_blue_over_red_at_exact_time(melt_bin, render_dir: Path):
    proj = _two_track_base()
    # place blue at t=2.0s for 1.0s (frames [50, 75)) on the upper track
    proj = patcher.patch_project(
        proj,
        [PlaceClip(track_ref="vtop", producer_id="blue", in_point=0, out_point=24,
                   at_frame=50, mode="overwrite")],
    )
    path = render_dir / "overwrite.kdenlive"
    serialize_project(proj, path)

    f_before = render_frame(path, 47, render_dir, melt_bin=melt_bin, name="ov_before.png")  # 1.88s
    f_during = render_frame(path, 62, render_dir, melt_bin=melt_bin, name="ov_during.png")  # 2.48s
    f_after = render_frame(path, 77, render_dir, melt_bin=melt_bin, name="ov_after.png")   # 3.08s

    assert _dominant(f_before) == "red", "before the placement should be the red base"
    assert _dominant(f_during) == "blue", "during the placement the blue overlay should show"
    assert _dominant(f_after) == "red", "after the placement the red base returns"


# ---------------------------------------------------------------------------
# insert -- ripple + duration growth
# ---------------------------------------------------------------------------

def _sequence_single_track() -> KdenliveProject:
    """One video track: red [0,50) then green [50,100). (+audio)"""
    p = KdenliveProject(title="insert", profile=ProjectProfile(width=W, height=H, fps=FPS))
    p.producers = [_prod("red", RED), _prod("green", GREEN), _prod("blue", BLUE)]
    p.tracks = [Track(id="v1", track_type="video"), Track(id="a1", track_type="audio")]
    p.playlists = [
        Playlist(id="v1", entries=[
            PlaylistEntry(producer_id="red", in_point=0, out_point=49),
            PlaylistEntry(producer_id="green", in_point=0, out_point=49),
        ]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "99"}
    return p


def test_insert_ripples_content_right_and_grows_duration(melt_bin, ffprobe_bin, render_dir: Path):
    base = _sequence_single_track()
    base_path = render_dir / "insert_base.kdenlive"
    serialize_project(base, base_path)
    # before insert: green sits at frame 60
    before_green = render_frame(base_path, 60, render_dir, melt_bin=melt_bin, name="ins_pre60.png")
    assert _dominant(before_green) == "green"

    # insert blue (25 frames) at frame 50 (the red|green cut)
    proj = patcher.patch_project(
        base,
        [PlaceClip(track_ref="v1", producer_id="blue", in_point=0, out_point=24,
                   at_frame=50, mode="insert")],
    )
    path = render_dir / "insert.kdenlive"
    serialize_project(proj, path)

    # frame 60 is now inside the inserted blue; the old green content moved to 60+25=85
    assert _dominant(render_frame(path, 60, render_dir, melt_bin=melt_bin, name="ins60.png")) == "blue"
    assert _dominant(render_frame(path, 85, render_dir, melt_bin=melt_bin, name="ins85.png")) == "green"
    # frame 40 (before the insert point) is unchanged red
    assert _dominant(render_frame(path, 40, render_dir, melt_bin=melt_bin, name="ins40.png")) == "red"

    # total duration grew from 100 to 125 frames
    base_dur = probe(render_video(base_path, render_dir / "ins_base.mp4", frames=100, melt_bin=melt_bin), ffprobe_bin=ffprobe_bin).duration
    new_dur = probe(render_video(path, render_dir / "ins_new.mp4", frames=125, melt_bin=melt_bin), ffprobe_bin=ffprobe_bin).duration
    assert base_dur is not None and new_dur is not None
    assert new_dur > base_dur + 0.7, f"insert should grow duration: {base_dur}s -> {new_dur}s"


# ---------------------------------------------------------------------------
# cross-track move
# ---------------------------------------------------------------------------

def _move_base() -> KdenliveProject:
    """Bottom = white full; middle = blue [0,25); top = empty. 3 video tracks."""
    p = KdenliveProject(title="move", profile=ProjectProfile(width=W, height=H, fps=FPS))
    p.producers = [_prod("white", WHITE), _prod("blue", BLUE)]
    p.tracks = [
        Track(id="vbase", track_type="video"),
        Track(id="vmid", track_type="video"),
        Track(id="vtop", track_type="video"),
        Track(id="a1", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="vbase", entries=[PlaylistEntry(producer_id="white", in_point=0, out_point=99)]),
        Playlist(id="vmid", entries=[PlaylistEntry(producer_id="blue", in_point=0, out_point=24)]),
        Playlist(id="vtop", entries=[]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "99"}
    return p


def test_cross_track_move_reveals_lower_and_shows_target(melt_bin, render_dir: Path):
    base = _move_base()
    base_path = render_dir / "move_base.kdenlive"
    serialize_project(base, base_path)
    # before: blue sits over white at frame 12
    assert _dominant(render_frame(base_path, 12, render_dir, melt_bin=melt_bin, name="mv_pre12.png")) == "blue"

    # move blue from vmid (track 1) to vtop (track 2), landing at frame 50
    proj = patcher.patch_project(
        base,
        [MoveClipToTrack(from_track_ref="vmid", clip_index=0, to_track_ref="vtop",
                         at_frame=50, mode="overwrite", close_gap=False)],
    )
    path = render_dir / "move.kdenlive"
    serialize_project(proj, path)

    # old position (frame 12) now reveals the lower white track
    assert _dominant(render_frame(path, 12, render_dir, melt_bin=melt_bin, name="mv12.png")) == "white"
    # new position (frame 62) shows the moved blue clip on top
    assert _dominant(render_frame(path, 62, render_dir, melt_bin=melt_bin, name="mv62.png")) == "blue"


# ---------------------------------------------------------------------------
# match-length
# ---------------------------------------------------------------------------

def test_match_length_places_exact_reference_span(melt_bin, render_dir: Path):
    """B-roll matched to a reference clip covers exactly its span (pixel proof).

    Base = white full; reference = red [40,90) on a middle track (50 frames);
    matched blue is placed on the top track at the reference start with the
    reference length. The boundary frames (89 blue, 90 white) prove the placed
    clip spans exactly [40,90) -- i.e. equals the reference length.
    """
    p = KdenliveProject(title="matched", profile=ProjectProfile(width=W, height=H, fps=FPS))
    p.producers = [_prod("white", WHITE), _prod("red", RED), _prod("blue", BLUE)]
    p.tracks = [
        Track(id="vbase", track_type="video"),
        Track(id="vref", track_type="video"),
        Track(id="vtop", track_type="video"),
        Track(id="a1", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="vbase", entries=[PlaylistEntry(producer_id="white", in_point=0, out_point=119)]),
        Playlist(id="vref", entries=[
            PlaylistEntry(producer_id="", in_point=0, out_point=39),        # blank [0,40)
            PlaylistEntry(producer_id="red", in_point=0, out_point=49),     # red [40,90)
            PlaylistEntry(producer_id="", in_point=0, out_point=29),        # blank [90,120)
        ]),
        Playlist(id="vtop", entries=[]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "119"}

    from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
    ref_len = cp.reference_length(p.playlists[1].entries, 0)
    ref_start = cp.clip_start_frame(p.playlists[1].entries, 0)
    assert (ref_len, ref_start) == (50, 40)

    proj = patcher.patch_project(
        p,
        [PlaceClip(track_ref="vtop", producer_id="blue", in_point=0, out_point=ref_len - 1,
                   at_frame=ref_start, mode="overwrite")],
    )
    path = render_dir / "matched.kdenlive"
    serialize_project(proj, path)

    # before the reference span: top empty -> white base shows
    assert _dominant(render_frame(path, 38, render_dir, melt_bin=melt_bin, name="m38.png")) == "white"
    # inside the span: matched blue B-roll shows
    assert _dominant(render_frame(path, 65, render_dir, melt_bin=melt_bin, name="m65.png")) == "blue"
    # last frame of the matched span is still blue ...
    assert _dominant(render_frame(path, 89, render_dir, melt_bin=melt_bin, name="m89.png")) == "blue"
    # ... and the very next frame is white again -> blue length == reference length
    assert _dominant(render_frame(path, 90, render_dir, melt_bin=melt_bin, name="m90.png")) == "white"


# ---------------------------------------------------------------------------
# melt acceptance for every mode
# ---------------------------------------------------------------------------

def test_melt_accepts_all_placement_modes(melt_bin, render_dir: Path):
    cases = {
        "overwrite": patcher.patch_project(
            _two_track_base(),
            [PlaceClip(track_ref="vtop", producer_id="blue", in_point=0, out_point=24,
                       at_frame=50, mode="overwrite")],
        ),
        "insert": patcher.patch_project(
            _sequence_single_track(),
            [PlaceClip(track_ref="v1", producer_id="blue", in_point=0, out_point=24,
                       at_frame=50, mode="insert")],
        ),
        "insert_ripple_all": patcher.patch_project(
            _sequence_with_guides(),
            [PlaceClip(track_ref="v1", producer_id="blue", in_point=0, out_point=24,
                       at_frame=50, mode="insert", ripple_all_tracks=True)],
        ),
        "move": patcher.patch_project(
            _move_base(),
            [MoveClipToTrack(from_track_ref="vmid", clip_index=0, to_track_ref="vtop",
                             at_frame=50, mode="overwrite")],
        ),
    }
    for name, proj in cases.items():
        path = render_dir / f"accept_{name}.kdenlive"
        serialize_project(proj, path)
        result = melt_accepts(path, melt_bin=melt_bin, frames=40)
        assert result.ok, f"melt rejected {name} placement:\n{result.stderr[-1500:]}"


def _sequence_with_guides() -> KdenliveProject:
    p = _sequence_single_track()
    p.guides = [Guide(position=70, label="marker")]
    return p
