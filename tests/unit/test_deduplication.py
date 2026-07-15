"""Unit tests for perceptual deduplication of frame candidates."""
from __future__ import annotations

import subprocess

import pytest

from workshop_video_brain.core.models import FrameCandidate, MediaAsset
from workshop_video_brain.edit_mcp.pipelines.visual_research.dedup import (
    compute_perceptual_hash,
    deduplicate,
    hamming_distance,
)


def _make_solid_image(path, color: str, size: int = 64) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={size}x{size}",
        "-frames:v",
        "1",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)


def _make_checker_image(path, size: int = 64) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={size}x{size}:rate=1",
        "-frames:v",
        "1",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)


def _candidate(source_id, timestamp: float, image_path) -> FrameCandidate:
    return FrameCandidate(
        source_id=source_id,
        timestamp_seconds=timestamp,
        image_path=str(image_path),
    )


@pytest.fixture
def asset():
    return MediaAsset(path="/tmp/video.mp4")


def test_compute_perceptual_hash_returns_hex_string(tmp_path, asset):
    image_path = tmp_path / "red.png"
    _make_solid_image(image_path, "red")

    phash = compute_perceptual_hash(image_path)

    assert phash is not None
    assert isinstance(phash, str)
    int(phash, 16)  # must be valid hex


def test_compute_perceptual_hash_missing_file_returns_none(tmp_path):
    missing = tmp_path / "does_not_exist.png"

    assert compute_perceptual_hash(missing) is None


def test_hamming_distance_identical_hashes_is_zero():
    assert hamming_distance("00ff00ff00ff00ff", "00ff00ff00ff00ff") == 0


def test_hamming_distance_differs_by_bit_count():
    assert hamming_distance("0000000000000000", "0000000000000001") == 1
    assert hamming_distance("0000000000000000", "ffffffffffffffff") == 64


def test_near_identical_frames_collapse_to_one(tmp_path, asset):
    image_a = tmp_path / "solid_a.png"
    image_b = tmp_path / "solid_b.png"
    _make_solid_image(image_a, "blue")
    _make_solid_image(image_b, "blue")

    candidate_a = _candidate(asset.id, 1.0, image_a)
    candidate_b = _candidate(asset.id, 2.0, image_b)

    kept, duplicate_map = deduplicate([candidate_a, candidate_b], threshold=8)

    assert len(kept) == 1
    assert kept[0].candidate_id == candidate_a.candidate_id
    assert duplicate_map[str(candidate_a.candidate_id)] == [str(candidate_b.candidate_id)]


def test_distinct_frames_both_survive(tmp_path, asset):
    image_a = tmp_path / "solid.png"
    image_b = tmp_path / "checker.png"
    _make_solid_image(image_a, "black")
    _make_checker_image(image_b)

    candidate_a = _candidate(asset.id, 1.0, image_a)
    candidate_b = _candidate(asset.id, 2.0, image_b)

    kept, duplicate_map = deduplicate([candidate_a, candidate_b], threshold=8)

    assert len(kept) == 2
    kept_ids = {c.candidate_id for c in kept}
    assert candidate_a.candidate_id in kept_ids
    assert candidate_b.candidate_id in kept_ids
    assert duplicate_map[str(candidate_a.candidate_id)] == []
    assert duplicate_map[str(candidate_b.candidate_id)] == []


def test_deduplicate_keeps_higher_ranked_candidate(tmp_path, asset):
    image_a = tmp_path / "solid_low.png"
    image_b = tmp_path / "solid_high.png"
    _make_solid_image(image_a, "green")
    _make_solid_image(image_b, "green")

    candidate_low = _candidate(asset.id, 1.0, image_a)
    candidate_high = _candidate(asset.id, 2.0, image_b)

    rank = {candidate_low.candidate_id: 0.1, candidate_high.candidate_id: 0.9}

    kept, duplicate_map = deduplicate(
        [candidate_low, candidate_high],
        threshold=8,
        rank_key=lambda c: rank[c.candidate_id],
    )

    assert len(kept) == 1
    assert kept[0].candidate_id == candidate_high.candidate_id
    assert duplicate_map[str(candidate_high.candidate_id)] == [str(candidate_low.candidate_id)]


def test_deduplicate_records_perceptual_hash_on_metrics(tmp_path, asset):
    image_path = tmp_path / "solid.png"
    _make_solid_image(image_path, "yellow")
    candidate = _candidate(asset.id, 1.0, image_path)

    deduplicate([candidate], threshold=8)

    assert candidate.metrics.dedup_hash is not None
    int(candidate.metrics.dedup_hash, 16)


def test_deduplicate_never_deletes_candidate_image_files(tmp_path, asset):
    image_a = tmp_path / "solid_a.png"
    image_b = tmp_path / "solid_b.png"
    _make_solid_image(image_a, "purple")
    _make_solid_image(image_b, "purple")

    candidate_a = _candidate(asset.id, 1.0, image_a)
    candidate_b = _candidate(asset.id, 2.0, image_b)

    deduplicate([candidate_a, candidate_b], threshold=8)

    assert image_a.exists()
    assert image_b.exists()
