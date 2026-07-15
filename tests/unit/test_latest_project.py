"""Regression tests for version-aware latest-project selection (§1.3)."""
from __future__ import annotations

import os
import time


from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project


class TestLatestProjectVersioned:
    def test_v12_beats_v2_lexicographic_bug(self, tmp_path):
        """slug_v10..v12 must beat slug_v2 despite sorting lexicographically first."""
        files = []
        for n in range(1, 13):  # slug_v1 .. slug_v12
            p = tmp_path / f"slug_v{n}.kdenlive"
            p.write_text("<mlt/>", encoding="utf-8")
            files.append(p)
        # Shuffle input order to prove selection is not order-dependent.
        import random
        random.shuffle(files)
        assert latest_project(files) == tmp_path / "slug_v12.kdenlive"

    def test_single_digit_boundary(self, tmp_path):
        files = [tmp_path / f"clip_v{n}.kdenlive" for n in (8, 9, 10, 11)]
        for p in files:
            p.write_text("x", encoding="utf-8")
        assert latest_project(files) == tmp_path / "clip_v11.kdenlive"

    def test_empty_returns_none(self):
        assert latest_project([]) is None


class TestLatestProjectFallback:
    def test_unversioned_uses_mtime(self, tmp_path):
        old = tmp_path / "alpha.kdenlive"
        new = tmp_path / "beta.kdenlive"
        old.write_text("x", encoding="utf-8")
        new.write_text("x", encoding="utf-8")
        # Force old to be older than new regardless of write order.
        past = time.time() - 1000
        os.utime(old, (past, past))
        assert latest_project([old, new]) == new

    def test_versioned_beats_unversioned(self, tmp_path):
        versioned = tmp_path / "slug_v1.kdenlive"
        plain = tmp_path / "freshly_written.kdenlive"
        versioned.write_text("x", encoding="utf-8")
        plain.write_text("x", encoding="utf-8")
        # Even though `plain` is newer, a versioned working copy is canonical.
        assert latest_project([versioned, plain]) == versioned
