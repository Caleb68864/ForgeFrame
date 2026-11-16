"""Kdenlive-versus-melt differential for the cumulative check pack."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import requires_ffmpeg_ffprobe, requires_kdenlive, requires_melt_ffmpeg
from tests.integration.external._check_pack import PackStep, build_check_pack
from tests.integration.external._oracle import (
    kdenlive_render, mean_volume_db, melt_render_full, video_frame_count, video_psnr,
)

pytestmark = [pytest.mark.external, requires_kdenlive, requires_melt_ffmpeg, requires_ffmpeg_ffprobe]

AUDIO_XFAIL: set[str] = set()
FRAMES_XFAIL: set[str] = set()
PACK_SLUGS = ("single_clip", "two_clips", "speed", "dissolve", "audio_fade", "effect_blur", "title")


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> list[PackStep]:
    return build_check_pack(tmp_path_factory.mktemp("kdenlive_pack"))


@pytest.fixture(scope="module")
def renders(tmp_path_factory) -> dict[str, tuple[Path, Path, Path]]:
    return {"_dir": tmp_path_factory.mktemp("kdenlive_renders")}


def _step(pack: list[PackStep], slug: str) -> PackStep:
    return next(step for step in pack if step.slug == slug)


def _rendered(renders, step, kdenlive_bin, melt_bin):
    if step.slug not in renders:
        root = renders["_dir"]
        kdenlive_path = root / f"{step.slug}_kdenlive.mp4"
        melt_path = root / f"{step.slug}_melt.mp4"
        playlist = root / f"{step.slug}_rebuilt.mlt"
        renders[step.slug] = (
            kdenlive_render(step.path, kdenlive_path, kdenlive_bin, capture_playlist=playlist),
            melt_render_full(step.path, melt_path, melt_bin),
            playlist,
        )
    return renders[step.slug]


def _params(xfails: set[str], reason: str):
    params = []
    for slug in PACK_SLUGS:
        if slug in xfails:
            params.append(pytest.param(slug, id=slug, marks=pytest.mark.xfail(strict=True, reason=reason)))
        else:
            params.append(pytest.param(slug, id=slug))
    return params


@pytest.mark.parametrize(
    "slug",
    _params(FRAMES_XFAIL, "Kdenlive drops effect_add filter (no kdenlive_id) -- docs/prompts/03-effects-kdenlive-identity.md"),
)
def test_frames_match(slug, pack, renders, kdenlive_bin, melt_bin, ffmpeg_bin):
    step = _step(pack, slug)
    k, m, playlist = _rendered(renders, step, kdenlive_bin, melt_bin)
    psnr = video_psnr(k, m, ffmpeg_bin)
    assert psnr >= 33.0, f"PSNR {psnr:.2f} dB below 33.0 for {step.path}; captured playlist: {playlist}"


@pytest.mark.parametrize("slug", PACK_SLUGS, ids=PACK_SLUGS)
def test_duration_match(slug, pack, renders, kdenlive_bin, melt_bin, ffprobe_bin):
    step = _step(pack, slug)
    k, m, playlist = _rendered(renders, step, kdenlive_bin, melt_bin)
    frames_k, frames_m = video_frame_count(k, ffprobe_bin), video_frame_count(m, ffprobe_bin)
    assert abs(frames_k - frames_m) <= 1, f"frame counts K/M={frames_k}/{frames_m} for {step.path}; captured playlist: {playlist}"


@pytest.mark.parametrize(
    "slug",
    _params(AUDIO_XFAIL, "audio lost on clip_insert -- docs/prompts/02-audio-on-insert.md"),
)
def test_audio_audible(slug, pack, renders, kdenlive_bin, melt_bin, ffmpeg_bin):
    step = _step(pack, slug)
    k, m, playlist = _rendered(renders, step, kdenlive_bin, melt_bin)
    volume_k, volume_m = mean_volume_db(k, ffmpeg_bin), mean_volume_db(m, ffmpeg_bin)
    assert volume_k > -60 and volume_m > -60, (
        f"mean_volume K/M={volume_k:.1f}/{volume_m:.1f} dB for {step.path}; captured playlist: {playlist}"
    )


def _lane_spans(project) -> list[list[tuple[bool, int, int]]]:
    """Per non-empty content lane: (is_gap, in, out) in timeline order."""
    lanes = []
    for playlist in project.playlists:
        spans = [(not e.producer_id, e.in_point, e.out_point) for e in playlist.entries]
        if spans:
            lanes.append(spans)
    return lanes


@pytest.mark.parametrize("slug", ("single_clip", "two_clips"), ids=("single_clip", "two_clips"))
def test_kdenlive_rewrite_imports_same_timeline(slug, pack, renders, kdenlive_bin, melt_bin):
    """Kdenlive 26.x writes in/out/length as timecode; importing its document
    must give back the frames we wrote (ROADMAP next #1)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    step = _step(pack, slug)
    _k, _m, playlist = _rendered(renders, step, kdenlive_bin, melt_bin)
    assert playlist.exists(), "Kdenlive did not write its regenerated document"
    assert 'in="00:' in playlist.read_text(), "expected a timecode document from Kdenlive"
    ours, theirs = parse_project(step.path), parse_project(playlist)
    assert _lane_spans(ours), f"empty timeline parsed from {step.path}"
    assert _lane_spans(theirs) == _lane_spans(ours), f"captured playlist: {playlist}"
