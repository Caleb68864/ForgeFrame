"""project_diff: changes between two project versions (prompt 22)."""
from __future__ import annotations

from tests._testkit import sequence_project
from workshop_video_brain.core.models.kdenlive import Guide, OpaqueElement, PlaylistEntry, Producer
from workshop_video_brain.core.models.timeline import (
    AddEffect,
    AddGuide,
    CreateTrack,
    MoveClip,
    RemoveClip,
    SetEffectEnabled,
    SetEffectParams,
    SetTrackMute,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.pipelines.project_diff import diff_projects, track_label

R, G, B = "0xff0000ff", "0x00ff00ff", "0x0000ffff"


def _base():
    return sequence_project([R, B, G])


def _media(project, pid="producer_1", path="/footage/take2.mp4"):
    for p in project.producers:
        if p.id == pid:
            p.properties = {"resource": path, "mlt_service": "avformat", "length": "200"}
            p.resource = path
    return project


def _one(diff, category, action):
    found = [c for c in diff["changes"] if c["category"] == category and c["action"] == action]
    assert found, diff["text"]
    return found[0]


def test_identical():
    diff = diff_projects(_base(), _base())
    assert diff["identical"] and diff["changes"] == [] and not diff["truncated"]


def test_track_label():
    project = patch_project(_base(), [CreateTrack(track_type="video", name="B-roll")])
    assert [track_label(project, i) for i in range(3)] == ["V1 (Video)", "A1 (Audio)", "V2 (B-roll)"]


def test_trim_names_track_and_clip():
    a = _media(_base())
    b = a.model_copy(deep=True)
    b.playlists[0].entries[1] = PlaylistEntry(producer_id="producer_1", in_point=5, out_point=24)
    change = _one(diff_projects(a, b), "clips", "trimmed")
    assert change["in_delta"] == 5 and "V1" in change["text"] and "take2.mp4" in change["text"]


def test_insert_is_one_added_clip_and_effects_follow():
    a = patch_project(_base(), [AddEffect(track_index=0, clip_index=2, effect_name="avfilter.negate")])
    b = a.model_copy(deep=True)
    b.playlists[0].entries.insert(0, PlaylistEntry(producer_id="producer_1", in_point=0, out_point=9))
    # The negate's clip moved from index 2 to 3; keep it attached (as the patcher would).
    b.opaque_elements = [OpaqueElement(tag=e.tag, position_hint=e.position_hint,
                                       xml_string=e.xml_string.replace('clip_index="2"', 'clip_index="3"'))
                         for e in b.opaque_elements]
    diff = diff_projects(a, b)
    clip_changes = [c for c in diff["changes"] if c["category"] == "clips"]
    assert [c["action"] for c in clip_changes].count("added") == 1
    assert {c["action"] for c in clip_changes} == {"added", "moved"}
    assert not [c for c in diff["changes"] if c["category"] == "effects"]


def test_remove_and_move():
    removed = diff_projects(_base(), patch_project(_base(), [RemoveClip(track_ref="playlist_video", clip_index=1)]))
    assert _one(removed, "clips", "removed")["clip"] == "producer_1"
    moved = diff_projects(_base(), patch_project(_base(), [MoveClip(track_ref="playlist_video", from_index=0, to_index=2)]))
    assert _one(moved, "clips", "moved")


def test_replaced():
    a = _base()
    b = a.model_copy(deep=True)
    b.playlists[0].entries[1] = PlaylistEntry(producer_id="producer_2", in_point=0, out_point=24)
    assert "replaced by producer_2" in _one(diff_projects(a, b), "clips", "replaced")["text"]


def test_effects_added_changed_disabled_removed_reordered():
    a = patch_project(_base(), [AddEffect(track_index=0, clip_index=0, effect_name="brightness", params={"level": "1"}),
                               AddEffect(track_index=0, clip_index=0, effect_name="avfilter.negate")])
    added = diff_projects(_base(), a)
    assert len([c for c in added["changes"] if c["category"] == "effects" and c["action"] == "added"]) == 2
    changed = diff_projects(a, patch_project(a, [SetEffectParams(track_index=0, clip_index=0, effect_index=0,
                                                                 params={"level": "0.3"})]))
    assert "level 1 -> 0.3" in _one(changed, "effects", "changed")["text"]
    disabled = diff_projects(a, patch_project(a, [SetEffectEnabled(track_index=0, clip_index=0, effect_index=1,
                                                                   enabled=False)]))
    assert "disabled" in _one(disabled, "effects", "disabled")["text"]
    keyframed = diff_projects(a, patch_project(a, [SetEffectParams(
        track_index=0, clip_index=0, effect_index=0, params={"level": "00:00:00.000=1;00:00:01.000=0"})]))
    assert "keyframes changed (1 -> 2 keyframes)" in _one(keyframed, "effects", "changed")["text"]
    b = a.model_copy(deep=True)
    b.opaque_elements = [e for e in b.opaque_elements if "negate" not in e.xml_string]
    assert _one(diff_projects(a, b), "effects", "removed")["effect"] == "avfilter.negate"
    c = a.model_copy(deep=True)
    c.opaque_elements = list(reversed(c.opaque_elements))
    assert _one(diff_projects(a, c), "effects", "reordered")


def test_tracks():
    a = _base()
    added = diff_projects(a, patch_project(a, [CreateTrack(track_type="video", name="B-roll")]))
    assert "V2 (B-roll)" in _one(added, "tracks", "added")["text"]
    renamed = a.model_copy(deep=True)
    renamed.tracks[0].name = "A-roll"
    assert _one(diff_projects(a, renamed), "tracks", "renamed")
    muted = diff_projects(a, patch_project(a, [SetTrackMute(track_ref="playlist_audio", muted=True)]))
    assert _one(muted, "tracks", "visibility_changed")
    gone = a.model_copy(deep=True)
    gone.tracks = gone.tracks[:1]
    gone.playlists = gone.playlists[:1]
    assert _one(diff_projects(a, gone), "tracks", "removed")


def _transition(**props):
    inner = "".join(f'<property name="{k}">{v}</property>' for k, v in props.items())
    return OpaqueElement(tag="transition", position_hint="tractor", xml_string=f"<transition>{inner}</transition>")


def test_transitions_and_timecode_equality():
    a = _base()
    a.opaque_elements.append(_transition(mlt_service="luma", kdenlive_id="dissolve", a_track=1, b_track=2,
                                         **{"in": 20, "out": 29}))
    tc = a.model_copy(deep=True)
    tc.opaque_elements = [_transition(mlt_service="luma", kdenlive_id="dissolve", a_track=1, b_track=2,
                                      **{"in": "00:00:00.800", "out": "00:00:01.160"})]
    assert diff_projects(a, tc)["identical"]
    moved = a.model_copy(deep=True)
    moved.opaque_elements = [_transition(mlt_service="luma", kdenlive_id="dissolve", a_track=1, b_track=2,
                                         **{"in": 40, "out": 49})]
    assert _one(diff_projects(a, moved), "transitions", "moved")
    assert _one(diff_projects(_base(), a), "transitions", "added")
    assert _one(diff_projects(a, _base()), "transitions", "removed")


def test_guides_bin_profile_duration():
    a = _base()
    b = patch_project(a, [AddGuide(position_frames=30, label="Step 2")])
    assert "Step 2" in _one(diff_projects(a, b), "guides", "added")["text"]
    relabel = b.model_copy(deep=True)
    relabel.guides = [Guide(position=30, label="Step two")]
    assert _one(diff_projects(b, relabel), "guides", "relabelled")
    assert _one(diff_projects(b, a), "guides", "removed")

    binned = a.model_copy(deep=True)
    binned.producers.append(Producer(id="new", resource="/footage/broll.mp4",
                                     properties={"resource": "/footage/broll.mp4"}))
    assert "broll.mp4" in _one(diff_projects(a, binned), "bin", "added")["text"]

    resized = a.model_copy(deep=True)
    resized.profile = resized.profile.model_copy(update={"width": 640})
    assert _one(diff_projects(a, resized), "profile", "changed")

    shorter = patch_project(a, [RemoveClip(track_ref="playlist_video", clip_index=2)])
    shorter = patch_project(shorter, [RemoveClip(track_ref="playlist_audio", clip_index=2)])
    change = _one(diff_projects(a, shorter), "duration", "changed")
    assert (change["old_frames"], change["new_frames"]) == (75, 50)
    assert "duration 0:03 -> 0:02" in diff_projects(a, shorter)["text"].splitlines()[0]


def test_truncation():
    a = _base()
    b = a.model_copy(deep=True)
    b.guides = [Guide(position=i, label=f"g{i}") for i in range(10)]
    diff = diff_projects(a, b, max_changes=3)
    assert diff["truncated"] and len(diff["changes"]) == 3
    assert diff["summary"]["guides"]["added"] == 10
