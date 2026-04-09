"""Tests for all TimelineIntent subclasses (MD-13)."""
from __future__ import annotations

import pytest
from workshop_video_brain.core.models.timeline import (
    AddClip,
    AddComposition,
    AddEffect,
    AddGuide,
    AddSubtitleRegion,
    AddTransition,
    AudioFade,
    CreateTrack,
    InsertGap,
    MoveClip,
    RemoveClip,
    RippleDelete,
    SetClipSpeed,
    SetTrackMute,
    SetTrackVisibility,
    SplitClip,
    SubtitleCue,
    TimelineIntent,
    TransitionIntent,
    TrimClip,
)


def test_timeline_intent_base_construction():
    ti = TimelineIntent()
    assert ti is not None


def test_transition_intent_defaults():
    t = TransitionIntent()
    assert t.type == ""
    assert t.track_ref == ""
    assert t.left_clip_ref == ""
    assert t.right_clip_ref == ""
    assert t.duration_frames == 0
    assert t.reason == ""


def test_subtitle_cue_defaults():
    s = SubtitleCue()
    assert s.start_seconds == 0.0
    assert s.end_seconds == 0.0
    assert s.text == ""


def test_add_clip_defaults():
    c = AddClip()
    assert c.producer_id == ""
    assert c.track_id == ""
    assert c.track_ref == ""
    assert c.in_point == 0
    assert c.out_point == 0
    assert c.position == -1
    assert c.source_path == ""


def test_add_clip_position_minus_one():
    c = AddClip()
    assert c.position == -1


def test_trim_clip_defaults():
    t = TrimClip()
    assert t.clip_ref == ""
    assert t.new_in == 0
    assert t.new_out == 0


def test_insert_gap_defaults():
    g = InsertGap()
    assert g.track_id == ""
    assert g.position == 0
    assert g.duration_frames == 0


def test_add_guide_defaults():
    g = AddGuide()
    assert g.position_frames == 0
    assert g.label == ""
    assert g.category is None
    assert g.comment is None


def test_add_guide_optional_none():
    g = AddGuide(category=None, comment=None)
    d = g.model_dump()
    assert d["category"] is None
    assert d["comment"] is None


def test_add_subtitle_region_defaults():
    s = AddSubtitleRegion()
    assert s.start_seconds == 0.0
    assert s.end_seconds == 0.0
    assert s.text == ""


def test_add_transition_defaults():
    t = AddTransition()
    assert t.type == ""
    assert t.track_ref == ""
    assert t.left_clip_ref == ""
    assert t.right_clip_ref == ""
    assert t.duration_frames == 0


def test_create_track_defaults():
    t = CreateTrack()
    assert t.track_type == "video"
    assert t.name == ""


def test_create_track_audio():
    t = CreateTrack(track_type="audio")
    assert t.track_type == "audio"


def test_remove_clip_defaults():
    r = RemoveClip()
    assert r.track_ref == ""
    assert r.clip_index == 0


def test_move_clip_defaults():
    m = MoveClip()
    assert m.track_ref == ""
    assert m.from_index == 0
    assert m.to_index == 0


def test_split_clip_defaults():
    s = SplitClip()
    assert s.track_ref == ""
    assert s.clip_index == 0
    assert s.split_at_frame == 0


def test_ripple_delete_defaults():
    r = RippleDelete()
    assert r.track_ref == ""
    assert r.clip_index == 0


def test_set_clip_speed_defaults():
    s = SetClipSpeed()
    assert s.track_ref == ""
    assert s.clip_index == 0
    assert s.speed == 1.0


def test_set_clip_speed_half_speed():
    s = SetClipSpeed(speed=0.5)
    assert s.speed == 0.5


def test_audio_fade_defaults():
    f = AudioFade()
    assert f.track_ref == ""
    assert f.clip_index == 0
    assert f.fade_type == "in"
    assert f.duration_frames == 24


def test_audio_fade_fade_out():
    f = AudioFade(fade_type="out")
    assert f.fade_type == "out"


def test_set_track_mute_defaults():
    m = SetTrackMute()
    assert m.track_ref == ""
    assert m.muted is True


def test_set_track_mute_unmute():
    m = SetTrackMute(muted=False)
    assert m.muted is False


def test_set_track_visibility_defaults():
    v = SetTrackVisibility()
    assert v.track_ref == ""
    assert v.visible is True


def test_set_track_visibility_hidden():
    v = SetTrackVisibility(visible=False)
    assert v.visible is False


def test_add_effect_defaults():
    e = AddEffect()
    assert e.track_index == 0
    assert e.clip_index == 0
    assert e.effect_name == ""
    assert e.params == {}


def test_add_effect_with_params():
    e = AddEffect(effect_name="brightness", params={"brightness": "0.5"})
    e2 = AddEffect.from_json(e.to_json())
    assert e2.params == {"brightness": "0.5"}


def test_add_composition_defaults():
    c = AddComposition()
    assert c.track_a == 0
    assert c.track_b == 0
    assert c.start_frame == 0
    assert c.end_frame == 0
    assert c.composition_type == ""
    assert c.params == {}


def test_add_composition_with_params():
    c = AddComposition(composition_type="luma", params={"alpha": "1"})
    c2 = AddComposition.from_json(c.to_json())
    assert c2.params == {"alpha": "1"}


def test_json_round_trip_sample():
    for cls, kwargs in [
        (AddClip, {"producer_id": "p1", "position": 5}),
        (AudioFade, {"fade_type": "out", "duration_frames": 12}),
        (AddEffect, {"effect_name": "gamma", "params": {"value": "1.2"}}),
        (AddComposition, {"composition_type": "mix", "params": {"mix": "50"}}),
    ]:
        obj = cls(**kwargs)
        obj2 = cls.from_json(obj.to_json())
        assert obj2 == obj


def test_yaml_round_trip_sample():
    for cls, kwargs in [
        (AddClip, {"producer_id": "p2", "track_ref": "v0"}),
        (AudioFade, {"track_ref": "a0", "clip_index": 2}),
        (AddEffect, {"effect_name": "blur", "params": {"radius": "5"}}),
        (AddComposition, {"track_a": 1, "track_b": 2, "start_frame": 0, "end_frame": 100}),
    ]:
        obj = cls(**kwargs)
        obj2 = cls.from_yaml(obj.to_yaml())
        assert obj2 == obj
