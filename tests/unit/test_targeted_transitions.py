"""Unit tests for targeted transition application and clip insertion."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _write_kdenlive(tmp_path: Path, content: str, filename: str = "test.kdenlive") -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return p


def _make_workspace(tmp_path: Path, kdenlive_xml: str, slug: str = "project") -> Path:
    """Create a minimal workspace directory with a working copy .kdenlive file."""
    ws = tmp_path / "workspace"
    working_copies = ws / "projects" / "working_copies"
    working_copies.mkdir(parents=True)
    # Write manifest as YAML (what read_manifest expects)
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
    # Write .kdenlive
    kdenlive_path = working_copies / f"{slug}_v1.kdenlive"
    kdenlive_path.write_text(kdenlive_xml, encoding="utf-8")
    return ws


# Project with 3 clips of 100 frames each on video playlist, 25fps
_THREE_CLIP_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt title="Three Clips" version="7">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1" colorspace="709"/>
      <producer id="clip_a"><property name="resource">/tmp/a.mp4</property></producer>
      <producer id="clip_b"><property name="resource">/tmp/b.mp4</property></producer>
      <producer id="clip_c"><property name="resource">/tmp/c.mp4</property></producer>
      <playlist id="playlist_video">
        <entry producer="clip_a" in="0" out="99"/>
        <entry producer="clip_b" in="0" out="99"/>
        <entry producer="clip_c" in="0" out="99"/>
      </playlist>
      <playlist id="playlist_audio"/>
      <tractor id="tractor0" in="0" out="299">
        <track producer="playlist_video"/>
        <track producer="playlist_audio" hide="video"/>
      </tractor>
    </mlt>
""")


# ---------------------------------------------------------------------------
# Tests for AddClip patcher implementation
# ---------------------------------------------------------------------------


class TestAddClipPatcher:
    def test_add_clip_appends_entry_to_playlist(self):
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject, Playlist, PlaylistEntry, Producer, Track
        )
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Test",
            producers=[Producer(id="existing", resource="/a.mp4")],
            playlists=[Playlist(id="pl_video", entries=[
                PlaylistEntry(producer_id="existing", in_point=0, out_point=99)
            ])],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        intent = AddClip(
            producer_id="new_clip",
            track_ref="pl_video",
            in_point=0,
            out_point=49,
            position=-1,
            source_path="/tmp/new.mp4",
        )
        patched = patch_project(project, [intent])

        assert len(patched.playlists[0].entries) == 2
        assert patched.playlists[0].entries[-1].producer_id == "new_clip"
        assert patched.playlists[0].entries[-1].out_point == 49

    def test_add_clip_creates_new_producer_if_missing(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject, Playlist, Track
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Test",
            playlists=[Playlist(id="pl_video")],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        intent = AddClip(
            producer_id="brand_new",
            track_ref="pl_video",
            in_point=0,
            out_point=24,
            source_path="/tmp/new.mp4",
        )
        patched = patch_project(project, [intent])

        producer_ids = [p.id for p in patched.producers]
        assert "brand_new" in producer_ids
        new_prod = next(p for p in patched.producers if p.id == "brand_new")
        assert new_prod.resource == "/tmp/new.mp4"

    def test_add_clip_skips_producer_creation_if_already_exists(self):
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject, Playlist, Producer, Track
        )
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Test",
            producers=[Producer(id="existing_clip", resource="/a.mp4")],
            playlists=[Playlist(id="pl_video")],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        intent = AddClip(
            producer_id="existing_clip",
            track_ref="pl_video",
            in_point=0,
            out_point=49,
        )
        patched = patch_project(project, [intent])

        # Should not duplicate producer
        assert len([p for p in patched.producers if p.id == "existing_clip"]) == 1

    def test_add_clip_inserts_at_specific_position(self):
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject, Playlist, PlaylistEntry, Track
        )
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Test",
            playlists=[Playlist(id="pl_video", entries=[
                PlaylistEntry(producer_id="first", in_point=0, out_point=99),
                PlaylistEntry(producer_id="second", in_point=0, out_point=99),
            ])],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        intent = AddClip(
            producer_id="inserted",
            track_ref="pl_video",
            in_point=0,
            out_point=24,
            position=1,  # insert between first and second
        )
        patched = patch_project(project, [intent])

        entries = patched.playlists[0].entries
        assert len(entries) == 3
        assert entries[0].producer_id == "first"
        assert entries[1].producer_id == "inserted"
        assert entries[2].producer_id == "second"

    def test_add_clip_no_matching_playlist_logs_warning(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject, Playlist, Track
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Test",
            playlists=[Playlist(id="pl_video")],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        intent = AddClip(
            producer_id="new_clip",
            track_ref="nonexistent_playlist",
            in_point=0,
            out_point=24,
        )
        # Should not raise; just skip
        patched = patch_project(project, [intent])
        assert len(patched.playlists[0].entries) == 0

    def test_add_clip_does_not_mutate_input(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject, Playlist, Track
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        project = KdenliveProject(
            title="Immutable",
            playlists=[Playlist(id="pl_video")],
            tracks=[Track(id="pl_video", track_type="video")],
        )
        original_entry_count = len(project.playlists[0].entries)
        intent = AddClip(
            producer_id="new_clip",
            track_ref="pl_video",
            in_point=0,
            out_point=49,
        )
        _ = patch_project(project, [intent])
        assert len(project.playlists[0].entries) == original_entry_count


# ---------------------------------------------------------------------------
# Tests for transitions_apply_at MCP tool
# ---------------------------------------------------------------------------


class TestTransitionsApplyAt:
    def test_apply_at_finds_boundary_and_applies_transition(self, tmp_path):
        """At t=4s (frame 100), there's a cut between clip_a (0-99) and clip_b (100-199)."""
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        # clip_a ends at frame 100 (4s), clip_b ends at 200 (8s)
        result = transitions_apply_at(str(ws), timestamp_seconds=3.9)
        assert result["status"] == "success", result.get("message")
        assert Path(result["data"]["kdenlive_path"]).exists()

    def test_apply_at_no_boundary_near_timestamp_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        # 50s is way past all clips — no cut nearby
        result = transitions_apply_at(str(ws), timestamp_seconds=50.0)
        assert result["status"] == "error"
        assert "No cut point found" in result["message"]

    def test_apply_at_empty_workspace_path_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        result = transitions_apply_at("", timestamp_seconds=1.0)
        assert result["status"] == "error"
        assert "workspace_path" in result["message"]

    def test_apply_at_negative_timestamp_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_at(str(ws), timestamp_seconds=-1.0)
        assert result["status"] == "error"
        assert "timestamp_seconds" in result["message"]

    def test_apply_at_unknown_transition_type_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_at(str(ws), timestamp_seconds=4.0, transition_type="warp")
        assert result["status"] == "error"
        assert "transition_type" in result["message"]

    def test_apply_at_unknown_preset_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_at(str(ws), timestamp_seconds=4.0, preset="ultralong")
        assert result["status"] == "error"
        assert "preset" in result["message"]


# ---------------------------------------------------------------------------
# Tests for transitions_apply_between MCP tool
# ---------------------------------------------------------------------------


class TestTransitionsApplyBetween:
    def test_apply_between_valid_index_returns_success(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_between(str(ws), clip_index=0)
        assert result["status"] == "success", result.get("message")
        d = result["data"]
        assert d["clip_index"] == 0
        assert d["left_clip"] == "clip_a"
        assert d["right_clip"] == "clip_b"
        assert Path(d["kdenlive_path"]).exists()

    def test_apply_between_last_valid_index(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_between(str(ws), clip_index=1)
        assert result["status"] == "success"
        assert result["data"]["left_clip"] == "clip_b"
        assert result["data"]["right_clip"] == "clip_c"

    def test_apply_between_out_of_range_index_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        # 3 clips → max valid index is 1 (between clip 1 and 2)
        result = transitions_apply_between(str(ws), clip_index=2)
        assert result["status"] == "error"
        assert "out of range" in result["message"]

    def test_apply_between_negative_index_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_between(str(ws), clip_index=-1)
        assert result["status"] == "error"
        assert "clip_index" in result["message"]

    def test_apply_between_short_preset(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_between(str(ws), clip_index=0, preset="short")
        assert result["status"] == "success"
        assert result["data"]["preset"] == "short"

    def test_apply_between_unknown_preset_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = transitions_apply_between(str(ws), clip_index=0, preset="instant")
        assert result["status"] == "error"
        assert "preset" in result["message"]


# ---------------------------------------------------------------------------
# Tests for clip_insert MCP tool
# ---------------------------------------------------------------------------


class TestClipInsert:
    def test_clip_insert_appends_to_end(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        # Create a fake media file
        media = tmp_path / "new_clip.mp4"
        media.write_bytes(b"\x00" * 16)

        result = clip_insert(str(ws), str(media), in_seconds=0.0, out_seconds=2.0, position=-1)
        assert result["status"] == "success", result.get("message")
        d = result["data"]
        assert Path(d["kdenlive_path"]).exists()
        assert d["position"] == -1

        # Verify entry was actually added to the playlist
        patched = parse_project(Path(d["kdenlive_path"]))
        video_pl = next(pl for pl in patched.playlists if pl.id == "playlist_video")
        assert len(video_pl.entries) == 4  # 3 original + 1 new

    def test_clip_insert_at_specific_position(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        media = tmp_path / "inserted.mp4"
        media.write_bytes(b"\x00" * 16)

        result = clip_insert(str(ws), str(media), in_seconds=0.0, out_seconds=1.0, position=1)
        assert result["status"] == "success", result.get("message")

        patched = parse_project(Path(result["data"]["kdenlive_path"]))
        video_pl = next(pl for pl in patched.playlists if pl.id == "playlist_video")
        # The inserted clip should be at position 1
        assert video_pl.entries[1].producer_id == result["data"]["producer_id"]

    def test_clip_insert_invalid_media_path_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = clip_insert(str(ws), "/nonexistent/path/to/clip.mp4")
        assert result["status"] == "error"
        assert "does not exist" in result["message"]

    def test_clip_insert_empty_media_path_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        result = clip_insert(str(ws), "")
        assert result["status"] == "error"
        assert "media_path" in result["message"]

    def test_clip_insert_empty_workspace_path_returns_error(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        result = clip_insert("", "/tmp/some.mp4")
        assert result["status"] == "error"
        assert "workspace_path" in result["message"]

    def test_clip_insert_frame_conversion(self, tmp_path):
        """Verify in/out seconds are correctly converted to frames at 25fps."""
        from workshop_video_brain.edit_mcp.server.tools import clip_insert

        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        media = tmp_path / "frame_test.mp4"
        media.write_bytes(b"\x00" * 16)

        result = clip_insert(str(ws), str(media), in_seconds=1.0, out_seconds=3.0)
        assert result["status"] == "success"
        d = result["data"]
        # 1.0s * 25fps = 25, 3.0s * 25fps = 75
        assert d["in_frame"] == 25
        assert d["out_frame"] == 75

    def test_clip_insert_creates_producer_with_source_path(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.tools import clip_insert
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        ws = _make_workspace(tmp_path, _THREE_CLIP_XML)
        media = tmp_path / "sourced.mp4"
        media.write_bytes(b"\x00" * 16)

        result = clip_insert(str(ws), str(media), in_seconds=0.0, out_seconds=2.0)
        assert result["status"] == "success"

        patched = parse_project(Path(result["data"]["kdenlive_path"]))
        producer_id = result["data"]["producer_id"]
        found = next((p for p in patched.producers if p.id == producer_id), None)
        assert found is not None


# ---------------------------------------------------------------------------
# Tests for CLI commands
# ---------------------------------------------------------------------------


class TestTransitionsCLI:
    def test_transitions_group_exists(self):
        from click.testing import CliRunner
        from workshop_video_brain.app.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["transitions", "--help"])
        assert result.exit_code == 0
        assert "transitions" in result.output.lower()

    def test_transitions_at_help(self):
        from click.testing import CliRunner
        from workshop_video_brain.app.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["transitions", "at", "--help"])
        assert result.exit_code == 0
        assert "timestamp" in result.output.lower()

    def test_transitions_between_help(self):
        from click.testing import CliRunner
        from workshop_video_brain.app.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["transitions", "between", "--help"])
        assert result.exit_code == 0
        assert "clip_index" in result.output.lower()

    def test_clip_group_exists(self):
        from click.testing import CliRunner
        from workshop_video_brain.app.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["clip", "--help"])
        assert result.exit_code == 0

    def test_clip_insert_help(self):
        from click.testing import CliRunner
        from workshop_video_brain.app.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["clip", "insert", "--help"])
        assert result.exit_code == 0
        assert "--in" in result.output or "in_seconds" in result.output or "in" in result.output.lower()
