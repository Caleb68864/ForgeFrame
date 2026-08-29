"""Scratch frames must never land beside the source video.

Regression for a real defect: ``extract_frame`` defaulted its output to
``video_path.parent``, so every pipeline that extracted a *burst* (candidate
generation, the research handshake, the ``research_video`` service) wrote its
scratch PNGs next to the user's media -- ``media/raw/`` is a protected tree --
and left every deduped/dropped candidate there as an orphan. Two concurrent
runs on the same file then raced on identical filenames (``WinError 32`` in
CI on Windows).

The source video is copied into ``tmp_path`` so each test owns its parent dir
and the assertion "nothing beside the source" is exact.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from tests._testkit import requires_ffmpeg_ffprobe
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.visual_research import ResearchConfig, ResearchRegion
from workshop_video_brain.edit_mcp.adapters.ffmpeg.frames import (
    extract_centered_burst,
    extract_frame_burst,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.pipelines.visual_research.candidates import generate_candidates
from workshop_video_brain.edit_mcp.pipelines.visual_research.handshake import generate_handshake
from workshop_video_brain.edit_mcp.pipelines.visual_research.service import research_video

_FIXTURE = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()


def _isolated_copy(tmp_path: Path) -> Path:
    src_dir = tmp_path / "media" / "raw"
    src_dir.mkdir(parents=True)
    dest = src_dir / _FIXTURE.name
    shutil.copyfile(_FIXTURE, dest)
    return dest


def _beside(video: Path) -> list[Path]:
    return [p for p in video.parent.iterdir() if p != video]


@requires_ffmpeg_ffprobe
def test_burst_with_output_dir_writes_only_there(tmp_path):
    video = _isolated_copy(tmp_path)
    out = tmp_path / "frames"

    frames = extract_frame_burst(video, 0.0, 1.0, interval_seconds=0.5, output_dir=out)

    assert frames
    assert all(Path(f.image_path).parent == out for f in frames)
    assert all(Path(f.image_path).exists() for f in frames)
    assert _beside(video) == []


@requires_ffmpeg_ffprobe
def test_centered_burst_forwards_output_dir(tmp_path):
    video = _isolated_copy(tmp_path)
    out = tmp_path / "frames"

    frames = extract_centered_burst(
        video, anchor_seconds=1.0, before_seconds=0.5, after_seconds=0.5,
        interval_seconds=0.5, output_dir=out,
    )

    assert frames
    assert all(Path(f.image_path).parent == out for f in frames)
    assert _beside(video) == []


@requires_ffmpeg_ffprobe
def test_generate_candidates_with_output_dir_leaves_source_dir_clean(tmp_path):
    video = _isolated_copy(tmp_path)
    duration = probe_media(video).duration_seconds
    source = MediaAsset(path=str(video), media_type="video", duration_seconds=duration)
    region = ResearchRegion(
        source_id=source.id, start_seconds=0.0, end_seconds=min(duration, 2.0),
    )
    out = tmp_path / "scratch"

    candidates = generate_candidates(video, region, source, ResearchConfig(), output_dir=out)

    assert candidates
    assert all(Path(c.image_path).parent == out for c in candidates)
    assert _beside(video) == []


@requires_ffmpeg_ffprobe
def test_handshake_leaves_only_survivors_in_candidates_dir(tmp_path):
    video = _isolated_copy(tmp_path)
    out = tmp_path / "run"

    manifest = generate_handshake(video, output_dir=out, start_seconds=0.0, end_seconds=2.0)

    assert manifest["candidates"]
    assert _beside(video) == []
    # Scratch dir is gone; candidates/ holds exactly the cand-NNN.png survivors.
    assert not [p for p in out.iterdir() if p.name.startswith(".frames-")]
    pngs = sorted(p.name for p in (out / "candidates").iterdir())
    assert pngs == sorted(f"{c['id']}.png" for c in manifest["candidates"])


@requires_ffmpeg_ffprobe
def test_research_video_service_leaves_source_dir_clean(tmp_path):
    video = _isolated_copy(tmp_path)
    out = tmp_path / "pkg"
    config = ResearchConfig()
    config.candidate_generation.max_candidates_per_region = 3
    config.windowing.maximum_region_seconds = 3.0

    manifest = research_video(video, config=config, output_dir=out)

    assert manifest.captures
    assert (out / "manifest.json").exists()
    assert _beside(video) == []
    # The returned manifest never points at the (now removed) scratch dir:
    # retained candidates point at their exported copy, the rest are blank.
    for capture in manifest.captures:
        assert any(c.image_path for c in capture.candidates)
        for c in capture.candidates:
            if c.image_path:
                assert Path(c.image_path).exists()
                assert Path(c.image_path).is_relative_to(out)


@requires_ffmpeg_ffprobe
def test_research_video_keep_candidates_retains_every_image(tmp_path):
    video = _isolated_copy(tmp_path)
    out = tmp_path / "pkg"
    config = ResearchConfig()
    config.candidate_generation.max_candidates_per_region = 3
    config.windowing.maximum_region_seconds = 3.0

    manifest = research_video(video, config=config, output_dir=out, keep_candidates=True)

    assert manifest.captures
    for capture in manifest.captures:
        for c in capture.candidates:
            assert c.image_path and Path(c.image_path).exists()
            assert Path(c.image_path).is_relative_to(out)
    assert _beside(video) == []
