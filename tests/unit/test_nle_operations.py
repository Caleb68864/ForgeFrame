"""Comprehensive tests for NLE (Non-Linear Editing) patcher operations and MCP tools."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_project(n_clips: int = 3, fps: float = 25.0):
    """Return a KdenliveProject with n_clips on the first video playlist."""
    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject,
        Playlist,
        PlaylistEntry,
        Producer,
        ProjectProfile,
        Track,
    )

    producers = [Producer(id=f"clip_{i}", resource=f"/tmp/{i}.mp4") for i in range(n_clips)]
    entries = [
        PlaylistEntry(producer_id=f"clip_{i}", in_point=0, out_point=99)
        for i in range(n_clips)
    ]
    return KdenliveProject(
        title="Test",
        profile=ProjectProfile(width=1920, height=1080, fps=fps),
        producers=producers,
        playlists=[
            Playlist(id="pl_video", entries=entries),
            Playlist(id="pl_audio"),
        ],
        tracks=[
            Track(id="pl_video", track_type="video"),
            Track(id="pl_audio", track_type="audio"),
        ],
    )


def _real_entries(project, playlist_id="pl_video"):
    for pl in project.playlists:
        if pl.id == playlist_id:
            return [e for e in pl.entries if e.producer_id]
    return []


_THREE_CLIP_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt title="Three Clips" version="7">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1" colorspace="709"/>
      <producer id="clip_0"><property name="resource">/tmp/0.mp4</property></producer>
      <producer id="clip_1"><property name="resource">/tmp/1.mp4</property></producer>
      <producer id="clip_2"><property name="resource">/tmp/2.mp4</property></producer>
      <playlist id="pl_video">
        <entry producer="clip_0" in="0" out="99"/>
        <entry producer="clip_1" in="0" out="99"/>
        <entry producer="clip_2" in="0" out="99"/>
      </playlist>
      <playlist id="pl_audio"/>
      <tractor id="tractor0" in="0" out="299">
        <track producer="pl_video"/>
        <track producer="pl_audio" hide="video"/>
      </tractor>
    </mlt>
""")


def _make_workspace(tmp_path: Path, kdenlive_xml: str = _THREE_CLIP_XML, slug: str = "project") -> Path:
    """Create a minimal workspace directory with a working copy .kdenlive file."""
    ws = tmp_path / "workspace"
    working_copies = ws / "projects" / "working_copies"
    working_copies.mkdir(parents=True)
    manifest_yaml = (
        f"workspace_id: 00000000-0000-0000-0000-000000000001\n"
        f"project_title: Test Project\n"
        f"slug: {slug}\n"
        f"status: idea\n"
        f"media_root: {ws / 'media' / 'raw'}\n"
        f"vault_note_path: ''\n"
        f"content_type: tutorial\n"
        f"created_at: '2024-01-01T00:00:00+00:00'\n"
        f"updated_at: '2024-01-01T00:00:00+00:00'\n"
    )
    (ws / "workspace.yaml").write_text(manifest_yaml, encoding="utf-8")
    kdenlive_path = working_copies / f"{slug}_v1.kdenlive"
    kdenlive_path.write_text(kdenlive_xml, encoding="utf-8")
    return ws


# ---------------------------------------------------------------------------
# RemoveClip tests
# ---------------------------------------------------------------------------


class TestRemoveClip:
    def test_remove_middle_clip(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        intent = RemoveClip(track_ref="pl_video", clip_index=1)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[0].producer_id == "clip_0"
        assert entries[1].producer_id == "clip_2"

    def test_remove_first_clip(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        intent = RemoveClip(track_ref="pl_video", clip_index=0)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[0].producer_id == "clip_1"

    def test_remove_last_clip(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        intent = RemoveClip(track_ref="pl_video", clip_index=2)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[-1].producer_id == "clip_1"

    def test_remove_invalid_index_is_skipped(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = RemoveClip(track_ref="pl_video", clip_index=99)
        patched = patch_project(project, [intent])

        # Should be a no-op
        assert len(_real_entries(patched)) == 2

    def test_remove_from_empty_playlist_is_skipped(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = RemoveClip(track_ref="pl_video", clip_index=0)
        patched = patch_project(project, [intent])

        assert len(_real_entries(patched)) == 0

    def test_remove_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        patch_project(project, [RemoveClip(track_ref="pl_video", clip_index=0)])
        assert len(_real_entries(project)) == 3  # original unchanged


# ---------------------------------------------------------------------------
# MoveClip tests
# ---------------------------------------------------------------------------


class TestMoveClip:
    def test_move_clip_forward(self):
        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        # Move clip_0 (index 0) to index 2
        intent = MoveClip(track_ref="pl_video", from_index=0, to_index=2)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 3
        assert entries[2].producer_id == "clip_0"

    def test_move_clip_backward(self):
        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        # Move clip_2 (index 2) to index 0
        intent = MoveClip(track_ref="pl_video", from_index=2, to_index=0)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 3
        assert entries[0].producer_id == "clip_2"

    def test_move_same_position_is_noop(self):
        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        intent = MoveClip(track_ref="pl_video", from_index=1, to_index=1)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert [e.producer_id for e in entries] == ["clip_0", "clip_1", "clip_2"]

    def test_move_invalid_from_index_skipped(self):
        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = MoveClip(track_ref="pl_video", from_index=99, to_index=0)
        patched = patch_project(project, [intent])

        assert len(_real_entries(patched)) == 2

    def test_move_invalid_to_index_skipped(self):
        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = MoveClip(track_ref="pl_video", from_index=0, to_index=99)
        patched = patch_project(project, [intent])

        assert len(_real_entries(patched)) == 2


# ---------------------------------------------------------------------------
# SplitClip tests
# ---------------------------------------------------------------------------


class TestSplitClip:
    def test_split_in_middle(self):
        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)  # one clip: in=0 out=99
        intent = SplitClip(track_ref="pl_video", clip_index=0, split_at_frame=50)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[0].in_point == 0
        assert entries[0].out_point == 49
        assert entries[1].in_point == 50
        assert entries[1].out_point == 99
        assert entries[0].producer_id == "clip_0"
        assert entries[1].producer_id == "clip_0"

    def test_split_at_very_start_clamped(self):
        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        # split_at_frame=0 is clamped to 1
        intent = SplitClip(track_ref="pl_video", clip_index=0, split_at_frame=0)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        # First entry: 0..0, second: 1..99
        assert entries[0].in_point == 0
        assert entries[1].in_point == 1

    def test_split_at_very_end_clamped(self):
        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)  # out=99, duration=99
        # split_at_frame=99 is clamped to 98
        intent = SplitClip(track_ref="pl_video", clip_index=0, split_at_frame=200)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[1].out_point == 99

    def test_split_invalid_index_skipped(self):
        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        intent = SplitClip(track_ref="pl_video", clip_index=99, split_at_frame=50)
        patched = patch_project(project, [intent])

        assert len(_real_entries(patched)) == 1

    def test_split_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        patch_project(project, [SplitClip(track_ref="pl_video", clip_index=0, split_at_frame=50)])
        assert len(_real_entries(project)) == 1


# ---------------------------------------------------------------------------
# RippleDelete tests
# ---------------------------------------------------------------------------


class TestRippleDelete:
    def test_ripple_delete_removes_clip_no_gap(self):
        from workshop_video_brain.core.models.timeline import RippleDelete
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        intent = RippleDelete(track_ref="pl_video", clip_index=1)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[0].producer_id == "clip_0"
        assert entries[1].producer_id == "clip_2"

    def test_ripple_delete_first_clip(self):
        from workshop_video_brain.core.models.timeline import RippleDelete
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(3)
        patched = patch_project(project, [RippleDelete(track_ref="pl_video", clip_index=0)])
        entries = _real_entries(patched)
        assert len(entries) == 2
        assert entries[0].producer_id == "clip_1"

    def test_ripple_delete_no_blank_entries_remain(self):
        from workshop_video_brain.core.models.timeline import RippleDelete
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        patched = patch_project(project, [RippleDelete(track_ref="pl_video", clip_index=0)])
        # No blank (gap) entries should be left
        all_entries = patched.playlists[0].entries
        blank = [e for e in all_entries if not e.producer_id]
        assert len(blank) == 0


# ---------------------------------------------------------------------------
# TrimClip tests
# ---------------------------------------------------------------------------


class TestTrimClip:
    def test_trim_in_point(self):
        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = TrimClip(clip_ref="pl_video:0", new_in=10, new_out=-1)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert entries[0].in_point == 10
        assert entries[0].out_point == 99  # unchanged

    def test_trim_out_point(self):
        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = TrimClip(clip_ref="pl_video:0", new_in=-1, new_out=80)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert entries[0].in_point == 0  # unchanged
        assert entries[0].out_point == 80

    def test_trim_both_points(self):
        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = TrimClip(clip_ref="pl_video:1", new_in=5, new_out=75)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert entries[1].in_point == 5
        assert entries[1].out_point == 75

    def test_trim_invalid_index_skipped(self):
        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        intent = TrimClip(clip_ref="pl_video:99", new_in=10, new_out=80)
        patched = patch_project(project, [intent])

        entries = _real_entries(patched)
        assert entries[0].in_point == 0

    def test_trim_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        patch_project(project, [TrimClip(clip_ref="pl_video:0", new_in=20, new_out=50)])
        entries = _real_entries(project)
        assert entries[0].in_point == 0
        assert entries[0].out_point == 99


# ---------------------------------------------------------------------------
# InsertGap tests
# ---------------------------------------------------------------------------


class TestInsertGap:
    def test_insert_gap_at_position(self):
        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = InsertGap(track_id="pl_video", position=1, duration_frames=50)
        patched = patch_project(project, [intent])

        all_entries = patched.playlists[0].entries
        assert len(all_entries) == 3
        # Position 1 should be a blank entry
        assert all_entries[1].producer_id == ""
        assert all_entries[1].out_point == 49  # 50 frames = out=49

    def test_insert_gap_at_beginning(self):
        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = InsertGap(track_id="pl_video", position=0, duration_frames=25)
        patched = patch_project(project, [intent])

        all_entries = patched.playlists[0].entries
        assert all_entries[0].producer_id == ""
        assert all_entries[1].producer_id == "clip_0"

    def test_insert_gap_at_end(self):
        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        intent = InsertGap(track_id="pl_video", position=2, duration_frames=25)
        patched = patch_project(project, [intent])

        all_entries = patched.playlists[0].entries
        assert len(all_entries) == 3
        assert all_entries[-1].producer_id == ""

    def test_insert_gap_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        patch_project(project, [InsertGap(track_id="pl_video", position=0, duration_frames=10)])
        assert len(project.playlists[0].entries) == 2


# ---------------------------------------------------------------------------
# CreateTrack tests
# ---------------------------------------------------------------------------


class TestCreateTrack:
    def test_add_video_track(self):
        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = CreateTrack(track_type="video", name="My Video Track")
        patched = patch_project(project, [intent])

        # Count video tracks
        video_tracks = [t for t in patched.tracks if t.track_type == "video"]
        assert len(video_tracks) == 2  # original + new
        new_track = video_tracks[-1]
        assert new_track.name == "My Video Track"

        # Corresponding playlist should exist
        playlist_ids = {p.id for p in patched.playlists}
        assert new_track.id in playlist_ids

    def test_add_audio_track(self):
        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = CreateTrack(track_type="audio", name="Music")
        patched = patch_project(project, [intent])

        audio_tracks = [t for t in patched.tracks if t.track_type == "audio"]
        assert len(audio_tracks) == 2  # original + new
        new_track = audio_tracks[-1]
        assert new_track.name == "Music"

    def test_add_track_creates_unique_id(self):
        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        patched = patch_project(project, [CreateTrack(track_type="video")])
        patched2 = patch_project(patched, [CreateTrack(track_type="video")])

        ids = [t.id for t in patched2.tracks]
        assert len(ids) == len(set(ids)), "Track IDs must be unique"

    def test_add_track_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        original_count = len(project.tracks)
        patch_project(project, [CreateTrack(track_type="video")])
        assert len(project.tracks) == original_count


# ---------------------------------------------------------------------------
# AudioFade tests
# ---------------------------------------------------------------------------


class TestAudioFade:
    """AudioFade now appends an EntryFilter inside the playlist entry,
    matching the v25 shape verified against ``audio-mix.kdenlive`` from
    the KDE test suite.  The previous opaque-element form was rejected
    by Kdenlive 25.x's bin loader."""

    def test_fade_in_adds_entry_filter(self):
        from workshop_video_brain.core.models.timeline import AudioFade
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        patched = patch_project(project, [
            AudioFade(track_ref="pl_video", clip_index=0,
                      fade_type="in", duration_frames=24)
        ])
        assert len(patched.opaque_elements) == 0

        entry = next(
            e for pl in patched.playlists for e in pl.entries if e.producer_id
        )
        assert len(entry.filters) == 1
        f = entry.filters[0]
        assert f.properties["mlt_service"] == "volume"
        assert f.properties["kdenlive_id"] == "fadein"
        assert f.properties["gain"] == "0"
        assert f.properties["end"] == "1"
        # fade-in starts at the entry's local frame 0
        assert f.in_frame == 0
        assert f.out_frame == 23  # 24-frame fade

    def test_fade_out_adds_entry_filter_at_tail(self):
        from workshop_video_brain.core.models.timeline import AudioFade
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        # The default _make_project entry has out_point such that the
        # entry covers (out_point - in_point + 1) frames.
        entry_orig = next(
            e for pl in project.playlists for e in pl.entries if e.producer_id
        )
        entry_count = entry_orig.out_point - entry_orig.in_point + 1

        patched = patch_project(project, [
            AudioFade(track_ref="pl_video", clip_index=0,
                      fade_type="out", duration_frames=12)
        ])
        entry = next(
            e for pl in patched.playlists for e in pl.entries if e.producer_id
        )
        f = entry.filters[0]
        assert f.properties["kdenlive_id"] == "fadeout"
        assert f.properties["gain"] == "1"
        assert f.properties["end"] == "0"
        # Tail fade: ends at the last frame, starts ``duration`` frames before.
        assert f.out_frame == entry_count - 1
        assert f.in_frame == entry_count - 12

    def test_fade_does_not_mutate_original(self):
        from workshop_video_brain.core.models.timeline import AudioFade
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        patch_project(project, [AudioFade(track_ref="pl_video", clip_index=0)])
        # Original project's entry filters list is untouched.
        assert all(
            len(e.filters) == 0
            for pl in project.playlists for e in pl.entries
        )


# ---------------------------------------------------------------------------
# SetTrackMute / Visibility tests
# ---------------------------------------------------------------------------


class TestSetTrackMute:
    def test_mute_track_sets_muted_flag(self):
        from workshop_video_brain.core.models.timeline import SetTrackMute
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = SetTrackMute(track_ref="pl_audio", muted=True)
        patched = patch_project(project, [intent])

        track = next(t for t in patched.tracks if t.id == "pl_audio")
        assert track.muted is True
        assert patched.opaque_elements == []

    def test_unmute_track_clears_muted_flag(self):
        from workshop_video_brain.core.models.timeline import SetTrackMute
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        # Pre-mute, then unmute
        project.tracks[1].muted = True
        intent = SetTrackMute(track_ref="pl_audio", muted=False)
        patched = patch_project(project, [intent])

        track = next(t for t in patched.tracks if t.id == "pl_audio")
        assert track.muted is False
        assert patched.opaque_elements == []

    def test_mute_unknown_track_is_skipped(self):
        from workshop_video_brain.core.models.timeline import SetTrackMute
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = SetTrackMute(track_ref="nonexistent", muted=True)
        patched = patch_project(project, [intent])

        assert all(t.muted is False for t in patched.tracks)
        assert patched.opaque_elements == []


class TestSetTrackVisibility:
    def test_hide_track_sets_hidden_flag(self):
        from workshop_video_brain.core.models.timeline import SetTrackVisibility
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = SetTrackVisibility(track_ref="pl_video", visible=False)
        patched = patch_project(project, [intent])

        track = next(t for t in patched.tracks if t.id == "pl_video")
        assert track.hidden is True
        assert patched.opaque_elements == []

    def test_show_track_clears_hidden_flag(self):
        from workshop_video_brain.core.models.timeline import SetTrackVisibility
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        project.tracks[0].hidden = True
        intent = SetTrackVisibility(track_ref="pl_video", visible=True)
        patched = patch_project(project, [intent])

        track = next(t for t in patched.tracks if t.id == "pl_video")
        assert track.hidden is False
        assert patched.opaque_elements == []

    def test_visibility_unknown_track_is_skipped(self):
        from workshop_video_brain.core.models.timeline import SetTrackVisibility
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(0)
        intent = SetTrackVisibility(track_ref="nonexistent", visible=False)
        patched = patch_project(project, [intent])

        assert all(t.hidden is False for t in patched.tracks)
        assert patched.opaque_elements == []


# ---------------------------------------------------------------------------
# SetClipSpeed tests
# ---------------------------------------------------------------------------


class TestSetClipSpeed:
    def test_speed_sets_entry_speed_and_rescales_duration(self):
        # SetClipSpeed now writes the speed onto the playlist entry (so the
        # serializer can emit a matching ``<producer mlt_service="timewarp">``)
        # and rescales the entry's out_point to reflect the timewarped
        # frame count.  The legacy opaque-element form was rejected by the
        # Kdenlive 25.x bin loader as "Effect: Remove".
        from workshop_video_brain.core.models.timeline import SetClipSpeed
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(2)
        # Find the entry's original duration before the patch.
        original_entry = next(
            e for pl in project.playlists for e in pl.entries if e.producer_id
        )
        original_count = original_entry.out_point - original_entry.in_point + 1

        intent = SetClipSpeed(track_ref="pl_video", clip_index=0, speed=2.0)
        patched = patch_project(project, [intent])

        # No opaque elements -- the speed lives on the entry now.
        assert len(patched.opaque_elements) == 0

        patched_entry = next(
            e for pl in patched.playlists for e in pl.entries if e.producer_id
        )
        assert patched_entry.speed == 2.0
        new_count = patched_entry.out_point - patched_entry.in_point + 1
        assert new_count == max(1, round(original_count / 2.0))

    def test_speed_invalid_index_skipped(self):
        from workshop_video_brain.core.models.timeline import SetClipSpeed
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = _make_project(1)
        intent = SetClipSpeed(track_ref="pl_video", clip_index=99, speed=0.5)
        patched = patch_project(project, [intent])

        assert len(patched.opaque_elements) == 0


# ---------------------------------------------------------------------------
# Model import tests (round-trip / export)
# ---------------------------------------------------------------------------


class TestNewIntentModels:
    def test_all_new_models_importable_from_core(self):
        from workshop_video_brain.core.models import (
            AudioFade,
            MoveClip,
            RemoveClip,
            RippleDelete,
            SetClipSpeed,
            SetTrackMute,
            SetTrackVisibility,
            SplitClip,
        )
        assert RemoveClip
        assert MoveClip
        assert SplitClip
        assert RippleDelete
        assert SetClipSpeed
        assert AudioFade
        assert SetTrackMute
        assert SetTrackVisibility

    def test_remove_clip_defaults(self):
        from workshop_video_brain.core.models.timeline import RemoveClip
        r = RemoveClip()
        assert r.track_ref == ""
        assert r.clip_index == 0

    def test_audio_fade_defaults(self):
        from workshop_video_brain.core.models.timeline import AudioFade
        a = AudioFade()
        assert a.fade_type == "in"
        assert a.duration_frames == 24

    def test_set_clip_speed_defaults(self):
        from workshop_video_brain.core.models.timeline import SetClipSpeed
        s = SetClipSpeed()
        assert s.speed == 1.0

    def test_all_models_serializable(self):
        from workshop_video_brain.core.models.timeline import (
            AudioFade,
            MoveClip,
            RemoveClip,
            RippleDelete,
            SetClipSpeed,
            SetTrackMute,
            SetTrackVisibility,
            SplitClip,
        )
        for cls in [RemoveClip, MoveClip, SplitClip, RippleDelete,
                    SetClipSpeed, AudioFade, SetTrackMute, SetTrackVisibility]:
            obj = cls()
            d = obj.model_dump()
            assert isinstance(d, dict)


# ---------------------------------------------------------------------------
# MCP tool error path tests
# ---------------------------------------------------------------------------


class TestMcpToolErrorPaths:
    """Test invalid inputs to MCP tools return error dicts."""

    def test_clip_remove_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_remove
        result = clip_remove("", 0)
        assert result["status"] == "error"

    def test_clip_remove_nonexistent_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_remove
        result = clip_remove("/nonexistent/path/xyz", 0)
        assert result["status"] == "error"

    def test_clip_move_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_move
        result = clip_move("", 0, 1)
        assert result["status"] == "error"

    def test_clip_split_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_split
        result = clip_split("", 0)
        assert result["status"] == "error"

    def test_clip_trim_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_trim
        result = clip_trim("", 0)
        assert result["status"] == "error"

    def test_clip_ripple_delete_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_ripple_delete
        result = clip_ripple_delete("", 0)
        assert result["status"] == "error"

    def test_clip_speed_zero_speed_is_error(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_speed
        result = clip_speed("/tmp", 0, speed=0.0)
        assert result["status"] == "error"
        assert "speed" in result["message"].lower()

    def test_clip_speed_negative_speed_is_error(self):
        from workshop_video_brain.edit_mcp.server.tools import clip_speed
        result = clip_speed("/tmp", 0, speed=-1.0)
        assert result["status"] == "error"

    def test_audio_fade_invalid_type(self):
        from workshop_video_brain.edit_mcp.server.tools import audio_fade
        result = audio_fade("/tmp", 0, fade_type="sideways")
        assert result["status"] == "error"
        assert "fade_type" in result["message"]

    def test_track_add_invalid_type(self):
        from workshop_video_brain.edit_mcp.server.tools import track_add
        result = track_add("/tmp", track_type="diagonal")
        assert result["status"] == "error"

    def test_gap_insert_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import gap_insert
        result = gap_insert("", 0, 1.0)
        assert result["status"] == "error"

    def test_gap_insert_negative_duration(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import gap_insert
        ws = _make_workspace(tmp_path)
        result = gap_insert(str(ws), 0, -1.0)
        assert result["status"] == "error"

    def test_track_mute_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import track_mute
        result = track_mute("", 0)
        assert result["status"] == "error"

    def test_track_visibility_empty_workspace(self):
        from workshop_video_brain.edit_mcp.server.tools import track_visibility
        result = track_visibility("", 0)
        assert result["status"] == "error"


class TestMcpToolOutOfRangeErrors:
    """Test out-of-range index errors for MCP tools with real workspaces."""

    def test_clip_remove_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_remove
        ws = _make_workspace(tmp_path)
        result = clip_remove(str(ws), clip_index=999)
        assert result["status"] == "error"
        assert "range" in result["message"].lower() or "out" in result["message"].lower()

    def test_clip_move_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_move
        ws = _make_workspace(tmp_path)
        result = clip_move(str(ws), from_index=999, to_index=0)
        assert result["status"] == "error"

    def test_clip_split_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_split
        ws = _make_workspace(tmp_path)
        result = clip_split(str(ws), clip_index=999, split_at_seconds=1.0)
        assert result["status"] == "error"

    def test_clip_trim_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_trim
        ws = _make_workspace(tmp_path)
        result = clip_trim(str(ws), clip_index=999, in_seconds=1.0)
        assert result["status"] == "error"

    def test_clip_ripple_delete_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_ripple_delete
        ws = _make_workspace(tmp_path)
        result = clip_ripple_delete(str(ws), clip_index=999)
        assert result["status"] == "error"

    def test_clip_speed_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_speed
        ws = _make_workspace(tmp_path)
        result = clip_speed(str(ws), clip_index=999, speed=2.0)
        assert result["status"] == "error"

    def test_track_mute_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_mute
        ws = _make_workspace(tmp_path)
        result = track_mute(str(ws), track_index=999)
        assert result["status"] == "error"

    def test_track_visibility_out_of_range(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_visibility
        ws = _make_workspace(tmp_path)
        result = track_visibility(str(ws), track_index=999)
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# MCP tool success path integration tests
# ---------------------------------------------------------------------------


class TestMcpToolSuccessPaths:
    """Smoke tests: tools return success with a real workspace."""

    def test_clip_remove_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_remove
        ws = _make_workspace(tmp_path)
        result = clip_remove(str(ws), clip_index=1)
        assert result["status"] == "success"
        assert "kdenlive_path" in result["data"]

    def test_clip_move_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_move
        ws = _make_workspace(tmp_path)
        result = clip_move(str(ws), from_index=0, to_index=2)
        assert result["status"] == "success"

    def test_clip_split_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_split
        ws = _make_workspace(tmp_path)
        result = clip_split(str(ws), clip_index=1, split_at_seconds=2.0)
        assert result["status"] == "success"

    def test_clip_trim_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_trim
        ws = _make_workspace(tmp_path)
        result = clip_trim(str(ws), clip_index=0, in_seconds=0.5, out_seconds=3.5)
        assert result["status"] == "success"

    def test_clip_ripple_delete_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_ripple_delete
        ws = _make_workspace(tmp_path)
        result = clip_ripple_delete(str(ws), clip_index=0)
        assert result["status"] == "success"

    def test_clip_speed_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_speed
        ws = _make_workspace(tmp_path)
        result = clip_speed(str(ws), clip_index=0, speed=0.5)
        assert result["status"] == "success"
        assert result["data"]["speed"] == 0.5

    def test_audio_fade_in_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_fade
        ws = _make_workspace(tmp_path)
        result = audio_fade(str(ws), clip_index=0, fade_type="in", duration_seconds=1.0)
        assert result["status"] == "success"

    def test_audio_fade_out_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import audio_fade
        ws = _make_workspace(tmp_path)
        result = audio_fade(str(ws), clip_index=0, fade_type="out", duration_seconds=0.5)
        assert result["status"] == "success"

    def test_track_add_video_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_add
        ws = _make_workspace(tmp_path)
        result = track_add(str(ws), track_type="video", name="Extra")
        assert result["status"] == "success"
        assert result["data"]["track_type"] == "video"

    def test_track_add_audio_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_add
        ws = _make_workspace(tmp_path)
        result = track_add(str(ws), track_type="audio")
        assert result["status"] == "success"

    def test_track_mute_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_mute
        ws = _make_workspace(tmp_path)
        result = track_mute(str(ws), track_index=0, muted=True)
        assert result["status"] == "success"
        assert result["data"]["muted"] is True

    def test_track_mute_unmute_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_mute
        ws = _make_workspace(tmp_path)
        result = track_mute(str(ws), track_index=0, muted=False)
        assert result["status"] == "success"
        assert result["data"]["muted"] is False

    def test_track_visibility_hide_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_visibility
        ws = _make_workspace(tmp_path)
        result = track_visibility(str(ws), track_index=0, visible=False)
        assert result["status"] == "success"
        assert result["data"]["visible"] is False

    def test_track_visibility_show_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import track_visibility
        ws = _make_workspace(tmp_path)
        result = track_visibility(str(ws), track_index=0, visible=True)
        assert result["status"] == "success"

    def test_gap_insert_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import gap_insert
        ws = _make_workspace(tmp_path)
        result = gap_insert(str(ws), position=1, duration_seconds=2.0)
        assert result["status"] == "success"
        assert result["data"]["duration_seconds"] == 2.0
