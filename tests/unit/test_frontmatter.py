"""Unit tests for Obsidian frontmatter utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.production_brain.notes.frontmatter import (
    merge_frontmatter,
    parse_note,
    write_note,
)


class TestParseNote:
    def test_parses_frontmatter_and_body(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Test\ntags: [a, b]\n---\n# Hello\n\nBody text.", encoding="utf-8")
        fm, body = parse_note(note)
        assert fm["title"] == "Test"
        assert fm["tags"] == ["a", "b"]
        assert "Hello" in body

    def test_empty_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("# Just a body\n", encoding="utf-8")
        fm, body = parse_note(note)
        assert fm == {}
        assert "Just a body" in body

    def test_body_does_not_include_frontmatter(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: X\n---\nBody only.", encoding="utf-8")
        fm, body = parse_note(note)
        assert "title:" not in body
        assert "---" not in body


class TestWriteNote:
    def test_writes_valid_frontmatter(self, tmp_path):
        note = tmp_path / "sub" / "note.md"
        write_note(note, {"title": "Hello", "status": "idea"}, "# Hello\n")
        text = note.read_text()
        assert text.startswith("---\n")
        assert "title: Hello" in text
        assert "# Hello" in text

    def test_creates_parent_dirs(self, tmp_path):
        note = tmp_path / "a" / "b" / "note.md"
        write_note(note, {}, "body")
        assert note.exists()

    def test_round_trip(self, tmp_path):
        note = tmp_path / "note.md"
        write_note(note, {"foo": "bar", "n": 42}, "# Title\n\ncontent")
        fm, body = parse_note(note)
        assert fm["foo"] == "bar"
        assert fm["n"] == 42
        assert "Title" in body


class TestMergeFrontmatter:
    def test_updates_win_on_conflict(self):
        result = merge_frontmatter({"title": "Old"}, {"title": "New"})
        assert result["title"] == "New"

    def test_preserves_unrelated_keys(self):
        result = merge_frontmatter({"title": "T", "tags": ["x"]}, {"status": "idea"})
        assert result["title"] == "T"
        assert result["tags"] == ["x"]
        assert result["status"] == "idea"

    def test_deep_merge_nested_dicts(self):
        existing = {"meta": {"author": "Alice", "version": 1}}
        updates = {"meta": {"version": 2, "lang": "en"}}
        result = merge_frontmatter(existing, updates)
        assert result["meta"]["author"] == "Alice"   # preserved
        assert result["meta"]["version"] == 2         # updated
        assert result["meta"]["lang"] == "en"         # added

    def test_lists_replaced_not_merged(self):
        result = merge_frontmatter({"tags": ["a", "b"]}, {"tags": ["c"]})
        assert result["tags"] == ["c"]

    def test_empty_updates_preserves_all(self):
        existing = {"title": "T", "status": "idea"}
        result = merge_frontmatter(existing, {})
        assert result == existing
