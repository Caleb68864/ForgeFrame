"""Unit tests for the perceptual near-duplicate pipeline (pure functions)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import clip_dupes as cd


class TestDHash:
    def test_single_pair_brighter_left_sets_bit(self):
        assert cd.dhash_from_pixels([[10, 5]]) == 1
        assert cd.dhash_from_pixels([[5, 10]]) == 0
        assert cd.dhash_from_pixels([[7, 7]]) == 0  # equal -> 0 (not strictly >)

    def test_multi_column_row_msb_first(self):
        # cols: 10>5 ->1 , 5>10 ->0  => 0b10 == 2
        assert cd.dhash_from_pixels([[10, 5, 10]]) == 0b10

    def test_multi_row_concatenates(self):
        # row0: [10,5]->1 ; row1: [5,10]->0  => 0b10 == 2
        assert cd.dhash_from_pixels([[10, 5], [5, 10]]) == 0b10

    def test_ragged_rows_rejected(self):
        with pytest.raises(ValueError):
            cd.dhash_from_pixels([[1, 2, 3], [1, 2]])

    def test_too_narrow_rejected(self):
        with pytest.raises(ValueError):
            cd.dhash_from_pixels([[1]])

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            cd.dhash_from_pixels([])

    def test_gray_bytes_matches_pixels(self):
        # 3x2 grid -> rows [[10,5,10],[5,10,5]]
        data = bytes([10, 5, 10, 5, 10, 5])
        expected = cd.dhash_from_pixels([[10, 5, 10], [5, 10, 5]])
        assert cd.dhash_from_gray_bytes(data, width=3, height=2) == expected

    def test_gray_bytes_short_buffer_rejected(self):
        with pytest.raises(ValueError):
            cd.dhash_from_gray_bytes(bytes([1, 2, 3]), width=3, height=2)


class TestHamming:
    def test_known_distances(self):
        assert cd.hamming_distance(0b0000, 0b0000) == 0
        assert cd.hamming_distance(0b1010, 0b0011) == 2
        assert cd.hamming_distance(0b1111, 0b0000) == 4
        assert cd.hamming_distance(0xFF, 0x00) == 8

    def test_symmetric(self):
        assert cd.hamming_distance(123, 456) == cd.hamming_distance(456, 123)


class TestFrameTimestamps:
    def test_even_bucket_centres(self):
        assert cd.frame_timestamps(10.0, 5) == [1.0, 3.0, 5.0, 7.0, 9.0]

    def test_single_frame_is_midpoint(self):
        assert cd.frame_timestamps(4.0, 1) == [2.0]

    def test_invalid_duration(self):
        with pytest.raises(ValueError):
            cd.frame_timestamps(0.0, 3)

    def test_invalid_n(self):
        with pytest.raises(ValueError):
            cd.frame_timestamps(10.0, 0)


class TestClipDistance:
    def test_identical_sets_zero(self):
        assert cd.clip_distance([1, 2, 3], [1, 2, 3]) == 0.0

    def test_best_match_tolerates_extra_frames(self):
        # every hash in A finds an exact match in B (B just has an extra frame)
        assert cd.clip_distance([0, 1], [0, 1, 0xFFFFFFFF]) == pytest.approx(
            # d_ab both 0; d_ba: 0->0, 1->0, 0xFFFFFFFF-> min dist to {0,1}
            (0 + 0 + 0 + 0 + cd.hamming_distance(0xFFFFFFFF, 1)) / 5
        )

    def test_empty_is_infinite(self):
        assert cd.clip_distance([], [1]) == float("inf")
        assert cd.clip_distance([1], []) == float("inf")


class TestClustering:
    def test_groups_close_excludes_far(self):
        far = 0xFFFFFFFFFFFFFFFF
        hashes = {"a": [0], "b": [1], "c": [far]}
        groups = cd.cluster_by_distance(hashes, threshold=2)
        assert len(groups) == 1
        assert set(groups[0]) == {"a", "b"}

    def test_transitive_merge(self):
        # a~b (dist1), b~c (dist1), a-c dist2 -> all one group at threshold 1.5
        hashes = {"a": [0b00], "b": [0b01], "c": [0b11]}
        groups = cd.cluster_by_distance(hashes, threshold=1.0)
        assert len(groups) == 1
        assert set(groups[0]) == {"a", "b", "c"}

    def test_no_duplicates_returns_empty(self):
        hashes = {"a": [0x0], "b": [0xFFFFFFFFFFFFFFFF]}
        assert cd.cluster_by_distance(hashes, threshold=5) == []

    def test_preserves_input_order_within_group(self):
        hashes = {"z": [0], "a": [1], "m": [0]}
        groups = cd.cluster_by_distance(hashes, threshold=2)
        assert groups[0] == ["z", "a", "m"]


class TestSimilarityScore:
    def test_zero_distance_is_100(self):
        assert cd.similarity_score(0.0) == 100.0

    def test_half_bits(self):
        assert cd.similarity_score(32.0) == 50.0

    def test_infinite_is_zero(self):
        assert cd.similarity_score(float("inf")) == 0.0


class TestCommandConstruction:
    def test_frame_extract_command_shape(self):
        cmd = cd.frame_extract_command(
            Path("/in/clip.mp4"), 2.5, Path("/tmp/f.png"), width=48
        )
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        # fast seek: -ss precedes -i
        assert cmd.index("-ss") < cmd.index("-i")
        assert "2.5000" in cmd
        assert cmd[cmd.index("-frames:v") + 1] == "1"
        assert "scale=48:-2" in cmd
        assert cmd[-1] == "/tmp/f.png"

    def test_frame_extract_clamps_negative_timestamp(self):
        cmd = cd.frame_extract_command(
            Path("a.mp4"), -1.0, Path("f.png")
        )
        assert cmd[cmd.index("-ss") + 1] == "0.0000"

    def test_signature_pair_command(self):
        cmd = cd.signature_pair_command(Path("a.mp4"), Path("b.mp4"))
        assert cmd.count("-i") == 2
        joined = " ".join(cmd)
        assert "signature=nb_inputs=2:detectmode=full" in joined
        assert cmd[-2:] == ["-f", "null"] or "null" in cmd


class TestSignatureParsing:
    def test_positive_match(self):
        stderr = (
            "[Parsed_signature_0 @ 0x1] matching of video 0 at 3.760000 and "
            "1 at 3.760000, 150 frames matching\n"
            "[Parsed_signature_0 @ 0x1] whole video matching\n"
        )
        v = cd.parse_signature_match(stderr)
        assert v["matched"] is True
        assert v["whole"] is True
        assert v["frames"] == 150
        assert v["at"] == (3.76, 3.76)

    def test_no_match(self):
        stderr = "[Parsed_signature_0 @ 0x1] no matching of video 0 and 1\n"
        v = cd.parse_signature_match(stderr)
        assert v["matched"] is False
        assert v["frames"] is None

    def test_whole_only_still_matched(self):
        stderr = "[Parsed_signature_0 @ 0x1] whole video matching\n"
        v = cd.parse_signature_match(stderr)
        assert v["matched"] is True
