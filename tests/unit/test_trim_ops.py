"""Slip / slide / replace / ripple-insert planners and intents (prompt 20)."""
from __future__ import annotations

import pytest

from tests._testkit import sequence_project
from workshop_video_brain.core.models.kdenlive import Guide, OpaqueElement, PlaylistEntry
from workshop_video_brain.core.models.timeline import (
    AddEffect,
    ReplaceClip,
    RippleInsert,
    SetClipSpeed,
    SlideClip,
    SlipClip,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.pipelines import trim_ops
from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_start_frame, playlist_length

R, G, B = "0xff0000ff", "0x00ff00ff", "0x0000ffff"


def E(pid, i, o):
    return PlaylistEntry(producer_id=pid, in_point=i, out_point=o)


def gap(n):
    return PlaylistEntry(producer_id="", in_point=0, out_point=n - 1)


def spans(entries):
    return [(e.producer_id, e.in_point, e.out_point) for e in entries]


# ---------------------------------------------------------------------------
# planners
# ---------------------------------------------------------------------------

def test_slip_moves_in_and_out_only():
    entries = [E("a", 10, 34), E("b", 0, 24)]
    out = trim_ops.plan_slip(entries, 0, 5, source_frames=100)
    assert spans(out) == [("a", 15, 39), ("b", 0, 24)]
    assert playlist_length(out) == playlist_length(entries)
    assert spans(entries)[0] == ("a", 10, 34)  # input untouched


@pytest.mark.parametrize("delta, frames, needle", [(-11, None, "before the source"),
                                                  (66, 100, "past the end")])
def test_slip_bounds(delta, frames, needle):
    with pytest.raises(ValueError, match=needle):
        trim_ops.plan_slip([E("a", 10, 34)], 0, delta, frames)


def test_slide_right_between_clips():
    entries = [E("a", 0, 24), E("b", 0, 24), E("c", 5, 29)]
    out = trim_ops.plan_slide(entries, 1, 5, prev_source_frames=35, next_source_frames=35)
    assert spans(out) == [("a", 0, 29), ("b", 0, 24), ("c", 10, 29)]
    assert playlist_length(out) == 75


def test_slide_left_grows_next_from_its_handle():
    entries = [E("a", 0, 24), E("b", 0, 24), E("c", 5, 29)]
    out = trim_ops.plan_slide(entries, 1, -5)
    assert spans(out) == [("a", 0, 19), ("b", 0, 24), ("c", 0, 29)]


def test_slide_eats_and_grows_blanks():
    entries = [gap(5), E("b", 0, 24), gap(10)]
    out = trim_ops.plan_slide(entries, 0, -5)  # the gap before is used up and removed
    assert spans(out) == [("b", 0, 24), ("", 0, 14)]
    out = trim_ops.plan_slide(entries, 0, 3)
    assert spans(out) == [("", 0, 7), ("b", 0, 24), ("", 0, 6)]


def test_slide_first_clip_right_makes_a_gap():
    out = trim_ops.plan_slide([E("a", 0, 24), E("b", 0, 24)], 0, 5)
    assert spans(out) == [("", 0, 4), ("a", 0, 24), ("b", 5, 24)]


@pytest.mark.parametrize("entries, delta, kwargs, needle", [
    ([E("a", 0, 24), E("b", 0, 24)], -3, {}, "nothing before"),          # first clip backwards
    ([E("a", 0, 24), E("b", 0, 24)], 3, {}, None),                       # (ok: control)
    ([E("a", 0, 24), E("b", 0, 2)], 5, {}, "shortened"),                 # next too short
    ([E("a", 0, 24), E("b", 0, 24), E("c", 0, 24)], 5, {"prev_source_frames": 27}, "spare source"),
    ([E("a", 0, 24), E("b", 0, 24), E("c", 0, 24)], -5, {}, "spare source"),  # c has no head handle
])
def test_slide_errors(entries, delta, kwargs, needle):
    index = 1 if len(entries) == 3 else 0
    if needle is None:
        trim_ops.plan_slide(entries, index, delta, **kwargs)
        return
    with pytest.raises(ValueError, match=needle):
        trim_ops.plan_slide(entries, index, delta, **kwargs)


def test_replace_keeps_length():
    out = trim_ops.plan_replace([E("a", 0, 24), E("b", 3, 12)], 1, "n", new_in=40)
    assert spans(out) == [("a", 0, 24), ("n", 40, 49)]
    with pytest.raises(ValueError, match="needs 10"):
        trim_ops.plan_replace([E("b", 3, 12)], 0, "n", new_in=95, source_frames=100)


def test_insert_frame_for():
    entries = [E("a", 0, 24), gap(5), E("b", 0, 9)]
    assert trim_ops.insert_frame_for(entries, 0) == 0
    assert trim_ops.insert_frame_for(entries, 1) == 30
    assert trim_ops.insert_frame_for(entries, 2) == 40


# ---------------------------------------------------------------------------
# intents: linked audio, untouched tracks, rule 14
# ---------------------------------------------------------------------------

def _seq():
    return sequence_project([R, B, G])  # colour producers have 10 spare frames


def _assert_audio_synced(project, clip_index):
    video, audio = project.playlists
    assert spans(audio.entries) == spans(video.entries)
    assert clip_start_frame(audio.entries, clip_index) == clip_start_frame(video.entries, clip_index)


def test_slip_intent_syncs_audio_and_raises_length():
    project = _seq()
    patched = patch_project(project, [SlipClip(track_ref="playlist_video", clip_index=1, delta_frames=20)])
    assert spans(patched.playlists[0].entries)[1] == ("producer_1", 20, 44)
    _assert_audio_synced(patched, 1)
    producer = next(p for p in patched.producers if p.id == "producer_1")
    assert producer.properties["length"] == "45"  # rule 14: raised to cover out 44
    assert all(playlist_length(a.entries) == playlist_length(b.entries)
               for a, b in zip(project.playlists, patched.playlists))


def test_slide_intent_syncs_audio():
    project = patch_project(_seq(), [SlipClip(track_ref="playlist_video", clip_index=2, delta_frames=5)])
    patched = patch_project(project, [SlideClip(track_ref="playlist_video", clip_index=1, delta_frames=5,
                                                prev_source_frames=35, next_source_frames=35)])
    assert spans(patched.playlists[0].entries) == [("producer_0", 0, 29), ("producer_1", 0, 24),
                                                   ("producer_2", 10, 29)]
    _assert_audio_synced(patched, 1)


def test_slide_refused_when_audio_cannot_follow():
    project = _seq()
    project.playlists[1].entries[2] = E("producer_2", 0, 1)  # different audio neighbour: too short
    _patched, report = patch_project(project, [SlideClip(track_ref="playlist_video", clip_index=1,
                                                         delta_frames=5)], with_report=True)
    assert report.all_skipped


def test_replace_intent_with_and_without_audio():
    project = _seq()
    with_audio = patch_project(project, [ReplaceClip(track_ref="playlist_video", clip_index=1,
                                                     producer_id="producer_2", new_in=3)])
    assert spans(with_audio.playlists[0].entries)[1] == ("producer_2", 3, 27)
    _assert_audio_synced(with_audio, 1)

    silent = patch_project(project, [ReplaceClip(track_ref="playlist_video", clip_index=1,
                                                 producer_id="producer_2", new_has_audio=False)])
    assert spans(silent.playlists[1].entries)[1] == ("", 0, 24)

    keep = patch_project(project, [ReplaceClip(track_ref="playlist_video", clip_index=1,
                                               producer_id="producer_2", replace_audio=False)])
    assert spans(keep.playlists[1].entries) == spans(project.playlists[1].entries)


def test_timewarp_clip_is_refused():
    project = patch_project(_seq(), [SetClipSpeed(track_ref="playlist_video", clip_index=1, speed=2.0)])
    for intent in (SlipClip(track_ref="playlist_video", clip_index=1, delta_frames=2),
                   SlideClip(track_ref="playlist_video", clip_index=1, delta_frames=2),
                   ReplaceClip(track_ref="playlist_video", clip_index=1, producer_id="producer_0")):
        _p, report = patch_project(project, [intent], with_report=True)
        assert report.all_skipped, intent


def test_bad_index_is_skipped():
    _p, report = patch_project(_seq(), [SlipClip(track_ref="playlist_video", clip_index=9, delta_frames=1)],
                               with_report=True)
    assert report.all_skipped


def _with_extras(project):
    project.guides = [Guide(position=10, label="early"), Guide(position=40, label="late")]
    project.opaque_elements.append(OpaqueElement(
        tag="transition", position_hint="tractor",
        xml_string='<transition id="t1"><property name="in">50</property>'
                   '<property name="out">60</property><property name="mlt_service">luma</property></transition>'))
    project.opaque_elements.append(OpaqueElement(
        tag="transition", position_hint="tractor",
        xml_string='<transition id="t2" in="00:00:02.400" out="00:00:02.800"><property name="mlt_service">luma</property></transition>'))
    return project


def test_ripple_insert_moves_everything_after():
    project = _with_extras(sequence_project([R, B]))  # 2 x 25 frames
    project = patch_project(project, [AddEffect(track_index=0, clip_index=1, effect_name="avfilter.negate")])
    patched = patch_project(project, [RippleInsert(track_ref="playlist_video", before_clip_index=1,
                                                   producer_id="producer_0", in_point=0, out_point=9)])
    video, audio = patched.playlists
    assert spans(video.entries) == [("producer_0", 0, 24), ("producer_0", 0, 9), ("producer_1", 0, 24)]
    assert spans(audio.entries) == spans(video.entries)
    assert [g.position for g in patched.guides] == [10, 50]
    xml = " ".join(e.xml_string for e in patched.opaque_elements if e.tag == "transition")
    assert '<property name="in">60</property>' in xml and '<property name="out">70</property>' in xml
    assert 'in="00:00:02.800"' in xml and 'out="00:00:03.200"' in xml  # 25 fps: +10 frames = +0.4 s
    # The negate followed its clip from index 1 to 2.
    assert [e["mlt_service"] for e in list_effects(patched, (0, 2))] == ["avfilter.negate"]
    assert list_effects(patched, (0, 1)) == []


def test_ripple_insert_without_audio_pads_the_audio_track():
    patched = patch_project(sequence_project([R, B]), [RippleInsert(
        track_ref="playlist_video", before_clip_index=1, producer_id="producer_0",
        in_point=0, out_point=9, with_audio=False)])
    assert spans(patched.playlists[1].entries) == [("producer_0", 0, 24), ("", 0, 9), ("producer_1", 0, 24)]


def test_ripple_insert_splits_other_tracks_and_keeps_filters():
    project = sequence_project([R, B])
    project.tracks.append(project.tracks[0].model_copy(update={"id": "playlist_v2", "name": "V2"}))
    project.playlists.append(project.playlists[0].model_copy(deep=True, update={"id": "playlist_v2"}))
    project.playlists[2].entries = [E("producer_1", 0, 34)]  # spans the insert frame 25
    project = patch_project(project, [AddEffect(track_index=2, clip_index=0, effect_name="avfilter.negate")])
    patched = patch_project(project, [RippleInsert(track_ref="playlist_video", before_clip_index=1,
                                                   producer_id="producer_0", in_point=0, out_point=9)])
    assert spans(patched.playlists[2].entries) == [("producer_1", 0, 24), ("", 0, 9), ("producer_1", 25, 34)]
    assert [len(list_effects(patched, (2, i))) for i in (0, 1)] == [1, 1]


def test_ripple_insert_refused_when_a_transition_spans_the_frame():
    project = sequence_project([R, B])
    project.opaque_elements.append(OpaqueElement(
        tag="transition", position_hint="tractor",
        xml_string='<transition><property name="in">20</property><property name="out">30</property></transition>'))
    patched, report = patch_project(project, [RippleInsert(
        track_ref="playlist_video", before_clip_index=1, producer_id="producer_0",
        in_point=0, out_point=9)], with_report=True)
    assert report.all_skipped
    assert spans(patched.playlists[0].entries) == spans(project.playlists[0].entries)
