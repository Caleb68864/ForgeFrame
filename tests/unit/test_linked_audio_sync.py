"""Clip edits keep the linked audio entry and the clip filters in step (no melt)."""
from __future__ import annotations

from tests._testkit import requires_ffmpeg, sequence_project
from workshop_video_brain.core.models.kdenlive import OpaqueElement, PlaylistEntry
from workshop_video_brain.core.models.timeline import (
    AddEffect, InsertGap, MoveClip, PlaceClip, RemoveClip, RippleDelete, SplitClip, TrimClip,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

R, G, B = "0xff0000ff", "0x00ff00ff", "0x0000ffff"


def _seq():
    return sequence_project([R, G, B])  # playlist_video + playlist_audio, mirrored


def spans(project, i):
    return [(e.producer_id, e.in_point, e.out_point) for e in project.playlists[i].entries]


def test_each_edit_mirrors_onto_the_audio_track():
    for intent in (TrimClip(clip_ref="playlist_video:1", new_in=3, new_out=20),
                   RemoveClip(track_ref="playlist_video", clip_index=1),
                   RippleDelete(track_ref="playlist_video", clip_index=0),
                   MoveClip(track_ref="playlist_video", from_index=0, to_index=2),
                   SplitClip(track_ref="playlist_video", clip_index=1, split_at_frame=10),
                   InsertGap(track_id="playlist_video", position=1, duration_frames=7)):
        patched = patch_project(_seq(), [intent])
        assert spans(patched, 1) == spans(patched, 0), type(intent).__name__


def test_opt_out_leaves_audio_alone():
    patched = patch_project(_seq(), [RemoveClip(track_ref="playlist_video", clip_index=1, sync_linked_audio=False)])
    assert len(patched.playlists[1].entries) == 3


def test_editing_the_audio_track_does_not_touch_video():
    patched = patch_project(_seq(), [RemoveClip(track_ref="playlist_audio", clip_index=1)])
    assert len(patched.playlists[0].entries) == 3 and len(patched.playlists[1].entries) == 2


def test_move_refused_when_audio_cannot_follow():
    project = _seq()
    project.playlists[1].entries[2] = PlaylistEntry(producer_id="producer_0", in_point=0, out_point=24)
    patched, report = patch_project(project, [MoveClip(track_ref="playlist_video", from_index=0, to_index=2)],
                                    with_report=True)
    assert report.all_skipped and spans(patched, 0) == spans(project, 0)


def _with_effects():
    return patch_project(_seq(), [AddEffect(track_index=0, clip_index=i, effect_name=f"fx{i}") for i in range(3)])


def _effect_names(project, clip):
    return [e["mlt_service"] for e in list_effects(project, (0, clip))]


def test_filters_follow_their_clips():
    removed = patch_project(_with_effects(), [RemoveClip(track_ref="playlist_video", clip_index=1)])
    assert [_effect_names(removed, i) for i in range(2)] == [["fx0"], ["fx2"]]
    moved = patch_project(_with_effects(), [MoveClip(track_ref="playlist_video", from_index=0, to_index=2)])
    assert [_effect_names(moved, i) for i in range(3)] == [["fx1"], ["fx2"], ["fx0"]]
    split = patch_project(_with_effects(), [SplitClip(track_ref="playlist_video", clip_index=1, split_at_frame=10)])
    assert [_effect_names(split, i) for i in range(4)] == [["fx0"], ["fx1"], ["fx1"], ["fx2"]]


def test_place_clip_audio_and_transition_guard():
    with_audio = patch_project(_seq(), [PlaceClip(track_ref="playlist_video", producer_id="producer_2", in_point=0,
                                                  out_point=9, at_frame=25, mode="insert", ripple_all_tracks=True,
                                                  with_audio=True)])
    assert spans(with_audio, 1) == spans(with_audio, 0)
    silent = patch_project(_seq(), [PlaceClip(track_ref="playlist_video", producer_id="producer_2", in_point=0,
                                              out_point=9, at_frame=25, mode="insert", ripple_all_tracks=True)])
    assert spans(silent, 1)[1] == ("", 0, 9)  # default: a gap keeps sync, no sound
    project = _seq()
    project.opaque_elements.append(OpaqueElement(tag="transition", position_hint="tractor", xml_string=(
        '<transition><property name="in">20</property><property name="out">30</property></transition>')))
    _p, report = patch_project(project, [PlaceClip(track_ref="playlist_video", producer_id="producer_2",
                                                   in_point=0, out_point=9, at_frame=25, mode="insert",
                                                   ripple_all_tracks=True)], with_report=True)
    assert report.all_skipped


@requires_ffmpeg
def test_clip_place_audio_defaults(tmp_path):
    """Insert brings the media's sound; overwrite (a cover shot) leaves the narration alone."""
    from tests._testkit import call_tool, make_test_clip
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.server.bundles.clip_place import clip_place
    from workshop_video_brain.workspace.manager import WorkspaceManager

    root = tmp_path / "ws"
    WorkspaceManager.create("Place", tmp_path, workspace_root=root)
    clip = make_test_clip(tmp_path / "av.mp4", duration=1.0, with_audio=True)
    rel = "projects/working_copies/p_v1.kdenlive"
    for mode, expect_sound in (("insert", True), ("overwrite", False)):
        serialize_project(_seq(), root / rel)
        result = call_tool(clip_place, str(root), rel, str(clip), 0, 1.0, out_seconds=0.4, mode=mode,
                           ripple_all_tracks=mode == "insert")
        assert result["status"] == "success", result
        audio = parse_project(root / rel).playlists[1]
        has_sound = any(e.producer_id and e.producer_id not in ("producer_0", "producer_1", "producer_2")
                        for e in audio.entries)
        assert has_sound is expect_sound, (mode, [(e.producer_id, e.in_point, e.out_point) for e in audio.entries])
