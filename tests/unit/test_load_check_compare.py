"""Comparing MLT's view of a project with our model; canned input only."""
from __future__ import annotations

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject, Playlist, PlaylistEntry, ProjectProfile,
)
from workshop_video_brain.edit_mcp.adapters.mlt.engine import compare_inspection


def _model() -> KdenliveProject:
    return KdenliveProject(
        profile=ProjectProfile(width=320, height=180, fps=30.0),
        playlists=[Playlist(id="v", entries=[
            PlaylistEntry(producer_id="a", in_point=0, out_point=24),
            PlaylistEntry(producer_id="", in_point=0, out_point=9),
            PlaylistEntry(producer_id="b", in_point=5, out_point=14),
        ])],
    )


def _inspection(**overrides) -> dict:
    clips = [
        {"start": 0, "in": 0, "out": 24, "producer_id": "a"},
        {"start": 35, "in": 5, "out": 14, "producer_id": "b"},
    ]
    result = {
        "profile": {"width": 320, "height": 180, "frame_rate_num": 30, "frame_rate_den": 1},
        "tracks": [{"id": "t", "playlists": [{"id": "v", "clips": clips}, {"id": "v_kdpair", "clips": []}]}],
    }
    result.update(overrides)
    return result


def _clips(inspection: dict) -> list[dict]:
    return inspection["tracks"][0]["playlists"][0]["clips"]


def _severities(items) -> list[str]:
    return [item.severity for item in items]


def test_matching_project_has_no_items():
    assert compare_inspection(_inspection(), _model()) == []


def test_profile_size_mismatch_is_an_error():
    inspection = _inspection(profile={"width": 640, "height": 180, "frame_rate_num": 30, "frame_rate_den": 1})
    items = compare_inspection(inspection, _model())
    assert _severities(items) == ["error"]
    assert "640" in items[0].message


def test_frame_rate_mismatch_is_an_error():
    inspection = _inspection(profile={"width": 320, "height": 180, "frame_rate_num": 30000, "frame_rate_den": 1001})
    assert _severities(compare_inspection(inspection, _model())) == ["error"]


def test_ntsc_rate_within_tolerance_matches():
    model = _model()
    model.profile.fps = 30000 / 1001
    inspection = _inspection(profile={"width": 320, "height": 180, "frame_rate_num": 30000, "frame_rate_den": 1001})
    assert compare_inspection(inspection, model) == []


def test_no_tracks_is_an_error():
    items = compare_inspection(_inspection(tracks=[]), _model())
    assert any("no sequence tracks" in item.message for item in items)


def test_model_playlist_missing_from_mlt_is_an_error():
    inspection = _inspection()
    inspection["tracks"][0]["playlists"][0]["id"] = "other"
    items = compare_inspection(inspection, _model())
    assert any(item.severity == "error" and "did not build" in item.message for item in items)


def test_empty_model_playlist_missing_from_mlt_is_fine():
    model = _model()
    model.playlists.append(Playlist(id="empty"))
    assert compare_inspection(_inspection(), model) == []


def test_unknown_mlt_playlist_with_clips_is_a_warning():
    inspection = _inspection()
    inspection["tracks"][0]["playlists"].append({"id": "extra", "clips": [{"start": 0, "in": 0, "out": 1}]})
    assert _severities(compare_inspection(inspection, _model())) == ["warning"]


def test_kdpair_and_empty_extras_are_ignored():
    inspection = _inspection()
    inspection["tracks"][0]["playlists"].append({"id": "x_kdpair", "clips": [{"start": 0, "in": 0, "out": 1}]})
    inspection["tracks"][0]["playlists"].append({"id": "empty", "clips": []})
    assert compare_inspection(inspection, _model()) == []


def test_clip_count_mismatch_is_an_error():
    inspection = _inspection()
    _clips(inspection).pop()
    items = compare_inspection(inspection, _model())
    assert _severities(items) == ["error"]
    assert "2 clips in the model, 1 in MLT" in items[0].message


def test_in_out_and_start_mismatches_are_errors_naming_both_values():
    for field, value in (("in", 6), ("out", 13), ("start", 34)):
        inspection = _inspection()
        _clips(inspection)[1][field] = value
        items = compare_inspection(inspection, _model())
        assert _severities(items) == ["error"], field
        assert field in items[0].message and str(value) in items[0].message
        assert items[0].location == "v[1]"


def test_blank_counts_toward_the_model_start():
    """Without the 10-frame blank the second clip's start would be 25."""
    inspection = _inspection()
    _clips(inspection)[1]["start"] = 25
    assert any("start" in item.message for item in compare_inspection(inspection, _model()))


def test_different_producer_is_a_warning():
    inspection = _inspection()
    _clips(inspection)[0]["producer_id"] = "z"
    assert _severities(compare_inspection(inspection, _model())) == ["warning"]


def test_the_serializers_audio_twin_is_the_same_producer():
    inspection = _inspection()
    _clips(inspection)[0]["producer_id"] = "a_kdaudio"
    assert compare_inspection(inspection, _model()) == []
