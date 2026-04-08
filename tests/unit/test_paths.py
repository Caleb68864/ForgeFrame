"""Unit tests for path and naming utilities."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from workshop_video_brain.core.utils.paths import (
    ensure_dir,
    safe_filename,
    versioned_path,
    workspace_relative,
)
from workshop_video_brain.core.utils.naming import slugify, timestamp_prefix


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


class TestSlugify:
    def test_lowercase(self):
        assert slugify("Hello World") == "hello-world"

    def test_strips_special_chars(self):
        result = slugify("Test (video) #1!")
        assert "(" not in result
        assert ")" not in result
        assert "#" not in result
        assert "!" not in result

    def test_collapses_hyphens(self):
        result = slugify("a  b   c")
        assert "--" not in result

    def test_strips_leading_trailing_hyphens(self):
        result = slugify("--hello--")
        assert not result.startswith("-")
        assert not result.endswith("-")


class TestTimestampPrefix:
    def test_format(self):
        ts = timestamp_prefix()
        # YYYY-MM-DD-HHMMSS
        parts = ts.split("-")
        assert len(parts) == 4
        assert len(parts[0]) == 4   # year
        assert len(parts[1]) == 2   # month
        assert len(parts[2]) == 2   # day
        assert len(parts[3]) == 6   # HHMMSS
