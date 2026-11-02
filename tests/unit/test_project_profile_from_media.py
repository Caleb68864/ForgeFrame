"""Timelines take their profile from the source media."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests._testkit import make_test_clip, requires_ffmpeg_ffprobe
from workshop_video_brain.core.models.assembly import AssemblyPlan, ClipAssignment, StepAssembly
from workshop_video_brain.edit_mcp.pipelines.assembly import assemble_timeline
from workshop_video_brain.edit_mcp.pipelines.project_profile import DEFAULT_PROFILE, profile_from_media
from workshop_video_brain.workspace.manager import WorkspaceManager

FIXTURE_2997 = Path(__file__).parents[1] / "fixtures/media_generated/test_clip_1080p2997_5s.mp4"


def test_fake_paths_fall_back_to_the_default():
    profile = profile_from_media(["/no/such/file.mp4", ""])
    assert profile == DEFAULT_PROFILE
    assert profile is not DEFAULT_PROFILE


@requires_ffmpeg_ffprobe
def test_first_usable_path_wins(tmp_path):
    clip = make_test_clip(tmp_path / "small.mp4", size=(320, 180), fps=30)
    profile = profile_from_media(["/no/such/file.mp4", clip])
    assert (profile.width, profile.height, profile.fps) == (320, 180, 30.0)


@requires_ffmpeg_ffprobe
def test_audio_only_file_is_skipped(tmp_path):
    tone = make_test_clip(tmp_path / "tone.wav", kind="tone")
    assert profile_from_media([tone]) == DEFAULT_PROFILE


@requires_ffmpeg_ffprobe
def test_ntsc_rate_is_exact():
    assert profile_from_media([FIXTURE_2997]).fps == 30000 / 1001


@requires_ffmpeg_ffprobe
def test_assembled_timeline_follows_its_source(tmp_path):
    clip = make_test_clip(tmp_path / "small.mp4", size=(320, 180), fps=30)
    root = tmp_path / "ws"
    WorkspaceManager.create("Profile", tmp_path, workspace_root=root)
    plan = AssemblyPlan(project_title="Profile", steps=[
        StepAssembly(step_number=1, clips=[
            ClipAssignment(clip_ref="small", source_path=str(clip), role="primary", in_seconds=0.0, out_seconds=1.0),
        ]),
    ])
    path = assemble_timeline(root, plan)
    profile = ET.parse(path).getroot().find("profile")
    assert (profile.get("width"), profile.get("height")) == ("320", "180")
    assert (profile.get("frame_rate_num"), profile.get("frame_rate_den")) == ("30", "1")
