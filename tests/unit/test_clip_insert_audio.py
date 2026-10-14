"""Audio/video pairing guarantees for timeline clip edits."""
from __future__ import annotations

from pathlib import Path

from tests._testkit import call_tool, make_test_clip, requires_ffmpeg_ffprobe

pytestmark = requires_ffmpeg_ffprobe


def _workspace(tmp_path: Path) -> Path:
    from workshop_video_brain.edit_mcp.server.tools import timeline_project, workspace_media

    media_root = tmp_path / "media"
    media_root.mkdir()
    result = call_tool(workspace_media.workspace_create, title="Audio insert test", media_root=str(media_root))
    assert result["status"] == "success", result
    root = Path(result["data"]["workspace_root"])
    created = call_tool(timeline_project.project_create_working_copy, str(root))
    assert created["status"] == "success", created
    return root


def _starts(playlist):
    starts = {}
    cursor = 0
    for entry in playlist.entries:
        if entry.producer_id:
            starts.setdefault(entry.producer_id, cursor)
        cursor += max(0, entry.out_point - entry.in_point + 1)
    return starts


def _latest(root: Path):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    project = max((root / "projects" / "working_copies").glob("*.kdenlive"), key=lambda p: p.stat().st_mtime)
    return parse_project(project)


def _tracks(project):
    audio_id = next(t.id for t in project.tracks if t.track_type == "audio")
    video_id = next(t.id for t in project.tracks if t.track_type == "video")
    return (next(p for p in project.playlists if p.id == video_id),
            next(p for p in project.playlists if p.id == audio_id))


def test_two_audio_inserts_align_and_share_source_points(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle

    root = _workspace(tmp_path)
    media = [make_test_clip(tmp_path / f"clip{i}.mp4", duration=2, with_audio=True, freq=440 + i * 100)
             for i in range(2)]
    results = [call_tool(clips_nle.clip_insert, str(root), str(path), out_seconds=1.96) for path in media]
    assert all(r["status"] == "success" and r["data"]["audio_placed"] for r in results)
    video, audio = _tracks(_latest(root))
    v_entries = [e for e in video.entries if e.producer_id]
    a_entries = [e for e in audio.entries if e.producer_id]
    assert len(v_entries) == len(a_entries) == 2
    assert [(e.producer_id, e.in_point, e.out_point) for e in v_entries] == [
        (e.producer_id, e.in_point, e.out_point) for e in a_entries
    ]
    assert _starts(video) == _starts(audio)


def test_video_only_insert_reports_unplaced_audio(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle

    root = _workspace(tmp_path)
    media = make_test_clip(tmp_path / "silent.mp4", duration=2, with_audio=False)
    result = call_tool(clips_nle.clip_insert, str(root), str(media), out_seconds=1.96)
    assert result["status"] == "success", result
    assert result["data"]["audio_placed"] is False


def test_append_pads_shorter_audio_playlist_to_video_start(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle

    root = _workspace(tmp_path)
    silent = make_test_clip(tmp_path / "silent_first.mp4", duration=2, with_audio=False)
    with_sound = make_test_clip(tmp_path / "sound_second.mp4", duration=2, with_audio=True)
    first = call_tool(clips_nle.clip_insert, str(root), str(silent), out_seconds=1.96)
    second = call_tool(clips_nle.clip_insert, str(root), str(with_sound), out_seconds=1.96)
    assert first["status"] == second["status"] == "success"
    assert second["data"]["audio_placed"] is True
    video, audio = _tracks(_latest(root))
    assert _starts(video)[second["data"]["producer_id"]] == _starts(audio)[second["data"]["producer_id"]]
    assert audio.entries[0].producer_id == ""


def test_speed_and_dissolve_keep_audio_start_aligned(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle, transitions

    root = _workspace(tmp_path)
    media = [make_test_clip(tmp_path / f"pair{i}.mp4", duration=3, with_audio=True, freq=440 + i * 100)
             for i in range(2)]
    for path in media:
        result = call_tool(clips_nle.clip_insert, str(root), str(path), out_seconds=2.96)
        assert result["status"] == "success" and result["data"]["audio_placed"]
    result = call_tool(clips_nle.clip_speed, str(root), 1, speed=2.0)
    assert result["status"] == "success", result
    video, audio = _tracks(_latest(root))
    assert _starts(video) == _starts(audio)
    result = call_tool(transitions.transitions_apply_between, str(root), 0)
    assert result["status"] == "success", result
    project = _latest(root)
    video, audio = _tracks(project)
    incoming = next(e for playlist in project.playlists if playlist.id != video.id and
                    any(t.id == playlist.id and t.track_type == "video" for t in project.tracks)
                    for e in playlist.entries if e.producer_id.endswith("_tw2"))
    incoming_playlist = next(playlist for playlist in project.playlists if incoming in playlist.entries)
    incoming_start = _starts(incoming_playlist)[incoming.producer_id]
    assert incoming_start == _starts(audio)[incoming.producer_id]


def test_audio_fade_is_native_and_attached_to_audio_playlist(tmp_path):
    from workshop_video_brain.edit_mcp.server.tools import clips_nle

    root = _workspace(tmp_path)
    media = make_test_clip(tmp_path / "fade.mp4", duration=3, with_audio=True)
    inserted = call_tool(clips_nle.clip_insert, str(root), str(media), out_seconds=2.96)
    assert inserted["status"] == "success"
    faded = call_tool(clips_nle.audio_fade, str(root), 0, fade_type="in", duration_seconds=1.0)
    assert faded["status"] == "success", faded
    project = _latest(root)
    audio_id = next(t.id for t in project.tracks if t.track_type == "audio")
    audio_index = next(i for i, p in enumerate(project.playlists) if p.id == audio_id)
    filters = [o.xml_string for o in project.opaque_elements if o.tag == "filter"]
    fade = next(xml for xml in filters if 'name="kdenlive_id">fadein' in xml)
    assert f'track="{audio_index}"' in fade
    assert 'in="0"' in fade and 'out="24"' in fade
