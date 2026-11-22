"""Beat-synced cuts, zooms and flashes (prompt 23)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, sequence_project
from workshop_video_brain.core.models.kdenlive import PlaylistEntry, Producer
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.pipelines import beat_sync
from workshop_video_brain.edit_mcp.pipelines.camera_moves import zoom_punch_train
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string
from workshop_video_brain.edit_mcp.server.bundles.beat_sync import beat_cut, beat_flash, beat_zoom
from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest

BEATS = [round(0.48 * i, 2) for i in range(1, 30)]  # every 12 frames at 25 fps


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

def test_select_strides_bars_phase_window_gap():
    beats = [float(i) for i in range(12)]
    assert beat_sync.select_beats(beats, "aggressive") == beats
    assert beat_sync.select_beats(beats, "medium") == [0, 2, 4, 6, 8, 10]
    # subtle: every 4th; bar beats (every 4th from phase) always kept
    assert beat_sync.select_beats(beats, "subtle") == [0, 4, 8]
    assert beat_sync.select_beats(beats, "subtle", phase=1) == [1, 5, 9]
    assert beat_sync.select_beats(beats, every_n=3) == [0, 3, 4, 6, 8, 9]  # 4 and 8 are bars
    assert beat_sync.select_beats(beats, "aggressive", start_s=3, end_s=6) == [3, 4, 5, 6]
    assert beat_sync.select_beats(beats, "aggressive", min_gap_s=2.5) == [0, 3, 6, 9]
    with pytest.raises(ValueError, match="subtle, medium, aggressive"):
        beat_sync.select_beats(beats, "wild")


def test_frames_through_a_trimmed_music_entry():
    frames, skipped = beat_sync.beats_to_timeline_frames([1.0, 2.0, 3.0, 9.0], 25.0, music_start_frame=100,
                                                         music_in_frame=40, music_out_frame=150)
    assert frames == [110, 135] and skipped == 2  # 1.0 s is before the in-point, 9.0 s after the out
    assert beat_sync.beats_to_timeline_frames([1.0], 25.0, offset_seconds=2.0) == ([75], 0)


def test_plan_beat_cut():
    records = [{"start": 0, "length": 20, "in": 0, "source_frames": 100},
               {"start": 20, "length": 20, "in": 0, "source_frames": 100},
               {"start": 40, "length": 20, "in": 0, "source_frames": 30}]
    plan = beat_sync.plan_beat_cut(records, [12, 24, 36, 48, 60, 72, 84], min_clip_frames=6)
    assert [(p["start"], p["new_length"], p["cut_frame"]) for p in plan] == [(0, 12, 12), (12, 12, 24), (24, 12, 36)]
    long_beats = beat_sync.plan_beat_cut(records, [50, 95], min_clip_frames=6)
    assert long_beats[0]["new_length"] == 50 and long_beats[1]["new_length"] == 45
    assert long_beats[2]["off_beat"] is False and long_beats[2]["new_length"] == 20  # no beat left: unchanged
    short_source = beat_sync.plan_beat_cut(records[2:], [80], min_clip_frames=6)
    assert short_source[0]["off_beat"] and short_source[0]["new_length"] == 30
    skip_close = beat_sync.plan_beat_cut(records[:1], [3, 15], min_clip_frames=6)
    assert skip_close[0]["new_length"] == 15
    with_gap = beat_sync.plan_beat_cut([records[0], dict(records[1], gap_before=5)], [12, 30], min_clip_frames=6)
    assert [p["start"] for p in with_gap] == [0, 17]


def test_clip_hits():
    records = [{"clip_index": 0, "start": 0, "length": 10}, {"clip_index": 1, "start": 15, "length": 10}]
    hits, missed = beat_sync.clip_hits(records, [3, 9, 12, 15, 24, 30])
    assert hits == {0: [3, 9], 1: [0, 9]} and missed == 1  # 12 is over the gap; 30 is past the end


def test_flash_and_zoom_pulses_merge():
    kfs = beat_sync.flash_keyframes([5, 7, 30], clip_length=40, strength=0.8, attack_frames=1, decay_frames=3)
    values = {k.frame: k.value for k in kfs}
    assert values[0] == 1.0 and values[5] == pytest.approx(1.8) and values[7] == pytest.approx(1.8)
    assert 8 not in values  # 5's decay (to 8) was cut by 7's attack at 6
    assert values[6] == 1.0 and values[33] == 1.0
    assert all(0 <= k.frame <= 39 for k in kfs)
    end = beat_sync.flash_keyframes([38], clip_length=40)
    assert max(k.frame for k in end) == 39
    train = zoom_punch_train(320, 180, [10, 30], 25.0, clip_length=50, intensity=0.2)
    rects = parse_keyframe_string("rect", train["rect"], fps=25.0)
    assert [k.frame for k in rects if k.value[2] > 320] == [10, 30]
    assert all(k.value[0] <= 0 and k.value[0] + k.value[2] >= 320 for k in rects)


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

def _grid(root: Path, beats=BEATS, source="/music/song.wav"):
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "beat_grid.json").write_text(json.dumps(
        {"bpm_estimate": 125.0, "period_seconds": 0.48, "beats": beats, "source": source}))


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Beats", tmp_path, workspace_root=root)
    project = sequence_project(["0xff0000ff", "0x0000ffff", "0x00ff00ff"], frames_each=20)
    for p in project.producers:
        p.properties["length"] = "200"
    serialize_versioned(project, root, read_manifest(root).slug)
    _grid(root)
    return root


def _latest(root):
    return parse_project(latest_project((root / "projects" / "working_copies").glob("*.kdenlive")))


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("beat_cut", "beat_zoom", "beat_flash")


def test_beat_cut_lands_on_beats_with_linked_audio(ws):
    data = _ok(call_tool(beat_cut, str(ws), every_n=1, music_offset_seconds=0.0))
    assert [c["cut_frame"] for c in data["clips"]] == [12, 24, 36]
    assert data["linked_audio_trimmed"] == 3
    assert data["shift_after_last_clip_frames"] == -24
    project = _latest(ws)
    video, audio = project.playlists
    assert [(e.in_point, e.out_point) for e in video.entries] == [(0, 11)] * 3
    assert [(e.in_point, e.out_point) for e in audio.entries] == [(0, 11)] * 3


def test_beat_cut_finds_music_by_file(ws, tmp_path):
    project = _latest(ws)
    music = tmp_path / "song.wav"
    music.write_bytes(b"RIFF")
    project.producers.append(Producer(id="music", resource=str(music),
                                      properties={"resource": str(music), "mlt_service": "avformat", "length": "400"}))
    project.playlists[1].entries = [PlaylistEntry(producer_id="music", in_point=0, out_point=59)]
    serialize_versioned(project, ws, read_manifest(ws).slug)
    _grid(ws, source=str(music))
    data = _ok(call_tool(beat_cut, str(ws), every_n=1))
    assert data["music"] == "entry" and data["music_start_frame"] == 0
    assert [c["cut_frame"] for c in data["clips"]] == [12, 24, 36]


def test_no_music_is_explained(ws):
    result = call_tool(beat_cut, str(ws))
    assert result["error_type"] == "invalid_input" and "music_offset_seconds" in result["suggestion"]


def test_missing_and_empty_grid(ws):
    (ws / "reports" / "beat_grid.json").unlink()
    assert call_tool(beat_cut, str(ws), music_offset_seconds=0.0)["error_type"] == "missing_file"
    _grid(ws, beats=[])
    assert call_tool(beat_cut, str(ws), music_offset_seconds=0.0)["error_type"] == "not_found"
    _grid(ws)
    assert call_tool(beat_cut, str(ws), track=3, music_offset_seconds=0.0)["error_type"] == "invalid_index"
    assert call_tool(beat_cut, str(ws), first_clip_index=5, music_offset_seconds=0.0)["error_type"] == "invalid_index"


def test_beat_zoom_and_flash_one_filter_per_clip(ws):
    zoom = _ok(call_tool(beat_zoom, str(ws), every_n=1, music_offset_seconds=0.0))
    assert [(c["clip_index"], c["beats"]) for c in zoom["clips"]] == [(0, 1), (1, 2), (2, 1)]
    flash = _ok(call_tool(beat_flash, str(ws), every_n=1, music_offset_seconds=0.0, strength=0.5))
    project = _latest(ws)
    for clip in range(3):
        services = [e["mlt_service"] for e in list_effects(project, (0, clip))]
        assert services == ["qtblend", "brightness"]
    level = list_effects(project, (0, 1))[1]["properties"]["level"]
    peaks = [k.frame for k in parse_keyframe_string("scalar", level, fps=25.0) if k.value > 1]
    assert peaks == [4, 16]  # beats at 24 and 36 on a clip starting at 20
    assert flash["beats_over_blanks"] == 0
