"""Source-time cuts map to timeline frames; hand-built projects, no binaries."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject, Playlist, PlaylistEntry, Producer, ProjectProfile, Track,
)
from workshop_video_brain.edit_mcp.pipelines.guides import cut_positions_on_timeline

SOURCE = Path("/media/a.mp4")


def _project() -> KdenliveProject:
    """Other clip 0-24, source 0-49, blank 10, source 100-149, at 25 fps."""
    return KdenliveProject(
        profile=ProjectProfile(fps=25.0),
        producers=[
            Producer(id="source", resource=str(SOURCE)),
            Producer(id="other", resource="/media/b.mp4"),
        ],
        playlists=[Playlist(id="v", entries=[
            PlaylistEntry(producer_id="other", in_point=0, out_point=24),
            PlaylistEntry(producer_id="source", in_point=0, out_point=49),
            PlaylistEntry(producer_id="", in_point=0, out_point=9),
            PlaylistEntry(producer_id="source", in_point=100, out_point=149),
        ])],
        tracks=[Track(id="v", track_type="video")],
    )


def test_cut_maps_into_the_placement_that_shows_it():
    # source second 1 = source frame 25, in the first placement at timeline 25 + 25.
    assert cut_positions_on_timeline(_project(), SOURCE, [1.0]) == [50]


def test_second_placement_uses_its_own_in_point():
    # source second 5 = frame 125; second placement starts at 25 + 50 + 10 = 85.
    assert cut_positions_on_timeline(_project(), SOURCE, [5.0]) == [85 + 25]


def test_cut_outside_every_placement_is_dropped():
    assert cut_positions_on_timeline(_project(), SOURCE, [3.0, 20.0]) == []


def test_results_are_sorted_and_deduplicated_across_tracks():
    project = _project()
    project.playlists.append(Playlist(id="a", entries=[e.model_copy() for e in project.playlists[0].entries]))
    project.tracks.append(Track(id="a", track_type="audio"))
    assert cut_positions_on_timeline(project, SOURCE, [5.0, 1.0]) == [50, 110]


def test_source_not_on_the_timeline_gives_nothing():
    assert cut_positions_on_timeline(_project(), Path("/media/absent.mp4"), [1.0]) == []


def test_speed_changed_placement_is_not_matched():
    project = _project()
    project.producers.append(Producer(id="warp", resource=f"2:{SOURCE}",
                                      properties={"mlt_service": "timewarp", "resource": f"2:{SOURCE}"}))
    project.playlists[0].entries[1].producer_id = "warp"
    assert cut_positions_on_timeline(project, SOURCE, [1.0]) == []
