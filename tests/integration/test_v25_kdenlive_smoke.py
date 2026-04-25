"""End-to-end smoke test for the v25 Kdenlive serializer.

Reproduces the MCP flow ``project_create_working_copy`` → ``clip_insert``
→ save, by calling the same underlying functions directly (no MCP server,
no FastMCP runtime).  Verifies the resulting file passes our v25 structural
assertions and parses cleanly back into the model.

Also writes the result to the user's Video Production folder so they can
open it in Kdenlive themselves.
"""
from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
    serialize_versioned,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    (ws / "projects" / "working_copies").mkdir(parents=True)
    (ws / "projects" / "snapshots").mkdir(parents=True)
    return ws


def _build_initial_project(title: str = "smoke_test") -> KdenliveProject:
    """Mirror what ``project_create_working_copy`` builds."""
    project = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=1920, height=1080, fps=29.97, colorspace="709"),
    )
    project.tracks = [
        Track(id="playlist_video", track_type="video", name="Video"),
        Track(id="playlist_audio", track_type="audio", name="Audio"),
    ]
    project.playlists = [
        Playlist(id="playlist_video"),
        Playlist(id="playlist_audio"),
    ]
    project.tractor = {"id": "main_seq", "in": "0", "out": "149"}
    return project


def _insert_clip(project: KdenliveProject, media_path: Path, fps: float = 29.97) -> KdenliveProject:
    """Mirror what ``clip_insert`` does after parsing the working copy."""
    duration_seconds = 5.0
    in_frame = 0
    out_frame = int(duration_seconds * fps) - 1

    audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    video_playlist = next(
        pl for pl in project.playlists if pl.id not in audio_playlist_ids
    )

    import hashlib
    stem = media_path.stem
    h = hashlib.md5(str(media_path).encode()).hexdigest()[:6]
    producer_id = f"{stem}_{h}"

    intent = AddClip(
        producer_id=producer_id,
        track_ref=video_playlist.id,
        track_id=video_playlist.id,
        in_point=in_frame,
        out_point=out_frame,
        position=-1,
        source_path=str(media_path),
    )
    return patch_project(project, [intent])


class TestV25EndToEnd:
    def test_create_then_insert_yields_v25_shape(self, workspace):
        # Step 1: project_create_working_copy
        project = _build_initial_project("smoke_test")
        v1 = serialize_versioned(project, workspace, "smoke_test")
        assert v1.exists(), "v1 .kdenlive was not written"

        # Sanity: v1 has all v25 markers
        root = ET.parse(v1).getroot()
        seq = next(
            (
                t for t in root.findall("tractor")
                if (t.get("id", "").count("-") == 4)  # uuid format
            ),
            None,
        )
        assert seq is not None, "main sequence tractor missing on initial project"

        # Step 2: parse v1 → patch → re-serialize (clip_insert path)
        if not TEST_CLIP.exists():
            pytest.skip(f"Generated test clip missing: {TEST_CLIP}")
        parsed = parse_project(v1)
        # Verify parser recovered both tracks (per-track tractor classification).
        assert len(parsed.tracks) == 2
        track_ids = {t.id for t in parsed.tracks}
        assert track_ids == {"playlist_video", "playlist_audio"}

        patched = _insert_clip(parsed, TEST_CLIP)

        v2 = serialize_versioned(patched, workspace, "smoke_test")
        assert v2.name == "smoke_test_v2.kdenlive"

        # The clip's playlist must contain at least one entry referencing the
        # generated producer.
        v2_root = ET.parse(v2).getroot()
        video_pl = v2_root.find("./playlist[@id='playlist_video']")
        assert video_pl is not None
        entry_producers = {e.get("producer") for e in video_pl.findall("entry")}
        # The producer id is a hash of the clip path; just verify there's >=1 entry.
        assert len(entry_producers) >= 1, (
            f"video playlist has no entries after clip_insert: refs={entry_producers}"
        )


@pytest.mark.skipif(
    not Path("C:/Users/CalebBennett/Videos/Video Production/tests").exists(),
    reason="User's Video Production tests folder not available",
)
def test_drop_smoke_output_in_user_test_folder(tmp_path):
    """Side-effect: write a fresh smoke output the user can try opening in Kdenlive."""
    if not TEST_CLIP.exists():
        pytest.skip(f"Generated test clip missing: {TEST_CLIP}")

    user_tests_dir = Path("C:/Users/CalebBennett/Videos/Video Production/tests")
    out_dir = user_tests_dir / "mcp_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Project_create_working_copy + clip_insert in one go.
    project = _build_initial_project("mcp_smoke_one_clip")
    parsed_after_create = project  # avoid round-trip noise here
    patched = _insert_clip(parsed_after_create, TEST_CLIP)

    out_path = out_dir / "001-one-clip.kdenlive"
    serialize_project(patched, out_path)
    assert out_path.exists()


@pytest.mark.skipif(
    not Path("C:/Users/CalebBennett/Videos/Test KdenLive").exists(),
    reason="User's Test KdenLive folder not available",
)
def test_drop_smoke_output_with_uhd_clip(tmp_path):
    """Smoke test using one of the user's real UHD source clips.

    Uses ``15647204_3840_2160_30fps.mp4`` (smallest, ~9MB) so Kdenlive can
    actually load and decode it.  Profile matches the source: 4K @ 30fps.
    """
    real_clip = Path("C:/Users/CalebBennett/Videos/Test KdenLive/15647204_3840_2160_30fps.mp4")
    if not real_clip.exists():
        pytest.skip(f"User's real test clip missing: {real_clip}")

    user_tests_dir = Path("C:/Users/CalebBennett/Videos/Video Production/tests")
    out_dir = user_tests_dir / "mcp_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 4K @ 30 fps
    project = KdenliveProject(
        version="7",
        title="mcp_smoke_uhd_clip",
        profile=ProjectProfile(width=3840, height=2160, fps=30.0, colorspace="709"),
    )
    project.tracks = [
        Track(id="playlist_video", track_type="video", name="Video"),
        Track(id="playlist_audio", track_type="audio", name="Audio"),
    ]
    project.playlists = [
        Playlist(id="playlist_video"),
        Playlist(id="playlist_audio"),
    ]
    project.tractor = {"id": "main_seq", "in": "0", "out": "0"}

    patched = _insert_clip(project, real_clip, fps=30.0)

    out_path = out_dir / "002-uhd-clip.kdenlive"
    serialize_project(patched, out_path)
    assert out_path.exists()
