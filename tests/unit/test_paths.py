"""Unit tests for path and naming utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.utils.paths import (
    ensure_dir,
    safe_filename,
    versioned_path,
    workspace_relative,
)


class TestSafeFilename:
    def test_strips_illegal_chars(self):
        result = safe_filename('my:file<name>"test"')
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result

    def test_replaces_spaces_with_hyphens(self):
        assert safe_filename("hello world") == "hello-world"

    def test_truncates_to_200_chars(self):
        long_name = "a" * 300
        assert len(safe_filename(long_name)) == 200

    def test_strips_backslash_and_pipe(self):
        result = safe_filename("file\\name|test")
        assert "\\" not in result
        assert "|" not in result

    def test_strips_question_mark_and_asterisk(self):
        result = safe_filename("what?is*this")
        assert "?" not in result
        assert "*" not in result

    def test_normal_name_unchanged(self):
        assert safe_filename("my-file.mp4") == "my-file.mp4"


class TestVersionedPath:
    def test_returns_base_when_no_collision(self, tmp_path):
        result = versioned_path(tmp_path / "project", ".kdenlive")
        assert result == tmp_path / "project.kdenlive"

    def test_increments_on_collision(self, tmp_path):
        (tmp_path / "project.kdenlive").touch()
        result = versioned_path(tmp_path / "project", ".kdenlive")
        assert result == tmp_path / "project-1.kdenlive"

    def test_increments_multiple_collisions(self, tmp_path):
        (tmp_path / "project.kdenlive").touch()
        (tmp_path / "project-1.kdenlive").touch()
        result = versioned_path(tmp_path / "project", ".kdenlive")
        assert result == tmp_path / "project-2.kdenlive"


class TestWorkspaceRelative:
    def test_returns_relative_string(self, tmp_path):
        absolute = tmp_path / "media" / "raw" / "clip.mp4"
        rel = workspace_relative(absolute, tmp_path)
        assert rel == str(Path("media/raw/clip.mp4"))

    def test_raises_for_outside_path(self, tmp_path):
        with pytest.raises(ValueError):
            workspace_relative("/some/other/path", tmp_path)


class TestEnsureDir:
    def test_creates_nested_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        result = ensure_dir(target)
        assert result.is_dir()
        assert result == target

    def test_idempotent(self, tmp_path):
        target = tmp_path / "dir"
        ensure_dir(target)
        ensure_dir(target)  # should not raise
        assert target.is_dir()


# NOTE: slugify() and timestamp_prefix() have a dedicated, comprehensive suite
# in test_naming.py (14 slugify cases + 6 timestamp cases). The former
# ``TestSlugify`` / ``TestTimestampPrefix`` classes here were byte-identical /
# strict-subset duplicates of that suite and were removed in the pass-4
# consolidation (coverage preserved by test_naming.py).
