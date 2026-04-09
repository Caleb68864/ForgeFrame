"""Unit tests for core/utils/naming.py — slugify and timestamp_prefix."""
from __future__ import annotations

import re

import pytest

from workshop_video_brain.core.utils.naming import slugify, timestamp_prefix


class TestSlugify:
    def test_spaces_become_hyphens(self):
        assert slugify("hello world") == "hello-world"

    def test_converts_to_lowercase(self):
        assert slugify("Hello World") == "hello-world"

    def test_multiple_spaces_become_single_hyphen(self):
        result = slugify("hello   world")
        assert result == "hello-world"

    def test_underscore_becomes_hyphen(self):
        result = slugify("hello_world")
        assert result == "hello-world"

    def test_special_chars_stripped(self):
        result = slugify("Test (video) #1!")
        assert "(" not in result
        assert ")" not in result
        assert "#" not in result
        assert "!" not in result

    def test_strips_leading_hyphens(self):
        result = slugify("--hello")
        assert not result.startswith("-")

    def test_strips_trailing_hyphens(self):
        result = slugify("hello--")
        assert not result.endswith("-")

    def test_collapses_multiple_hyphens(self):
        result = slugify("a--b---c")
        assert "--" not in result

    def test_empty_string_returns_empty(self):
        assert slugify("") == ""

    def test_only_special_chars_returns_empty(self):
        result = slugify("!!!###")
        assert result == ""

    def test_unicode_letters_preserved(self):
        # Unicode word chars (\w matches unicode by default in Python 3)
        result = slugify("café latte")
        assert "caf" in result
        assert " " not in result

    def test_numbers_preserved(self):
        result = slugify("step 1 tutorial")
        assert "1" in result

    def test_mixed_case_and_numbers(self):
        result = slugify("My Tutorial v2.0")
        assert result == "my-tutorial-v20"

    def test_already_slugified_unchanged(self):
        result = slugify("already-slugified")
        assert result == "already-slugified"


class TestTimestampPrefix:
    def test_returns_string(self):
        ts = timestamp_prefix()
        assert isinstance(ts, str)

    def test_format_has_four_hyphen_parts(self):
        ts = timestamp_prefix()
        parts = ts.split("-")
        assert len(parts) == 4

    def test_year_part_is_four_digits(self):
        ts = timestamp_prefix()
        year = ts.split("-")[0]
        assert len(year) == 4
        assert year.isdigit()

    def test_month_part_is_two_digits(self):
        ts = timestamp_prefix()
        month = ts.split("-")[1]
        assert len(month) == 2
        assert month.isdigit()

    def test_day_part_is_two_digits(self):
        ts = timestamp_prefix()
        day = ts.split("-")[2]
        assert len(day) == 2
        assert day.isdigit()

    def test_time_part_is_six_digits(self):
        ts = timestamp_prefix()
        time_part = ts.split("-")[3]
        assert len(time_part) == 6
        assert time_part.isdigit()

    def test_full_format_matches_pattern(self):
        ts = timestamp_prefix()
        assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}$", ts), f"Bad timestamp format: {ts}"

    def test_successive_calls_are_valid(self):
        ts1 = timestamp_prefix()
        ts2 = timestamp_prefix()
        # Both must match the pattern
        pattern = r"^\d{4}-\d{2}-\d{2}-\d{6}$"
        assert re.match(pattern, ts1)
        assert re.match(pattern, ts2)
