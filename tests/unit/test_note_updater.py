"""Unit tests for the Obsidian note updater."""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.production_brain.notes.updater import (
    append_section,
    update_frontmatter,
    update_section,
)


def _make_note(tmp_path: Path, content: str) -> Path:
    note = tmp_path / "note.md"
    note.write_text(content, encoding="utf-8")
    return note


BOUNDED_NOTE = """\
---
title: Test
status: idea
---

# Test Note

<!-- wvb:section:summary -->
Original content.
<!-- /wvb:section:summary -->

After section.
"""

UNBOUNDED_NOTE = """\
---
title: Test
---

# Test Note

No section markers here.
"""


class TestUpdateSection:
    def test_replaces_bounded_content(self, tmp_path):
        note = _make_note(tmp_path, BOUNDED_NOTE)
        update_section(note, "summary", "New content.")
        text = note.read_text()
        assert "New content." in text
        assert "Original content." not in text

    def test_preserves_content_outside_section(self, tmp_path):
        note = _make_note(tmp_path, BOUNDED_NOTE)
        update_section(note, "summary", "Updated.")
        text = note.read_text()
        assert "After section." in text
        assert "# Test Note" in text

    def test_appends_when_no_boundaries(self, tmp_path):
        note = _make_note(tmp_path, UNBOUNDED_NOTE)
        update_section(note, "summary", "Appended.")
        text = note.read_text()
        assert "Appended." in text
        # Original content untouched
        assert "No section markers here." in text

    def test_appended_section_has_boundaries(self, tmp_path):
        note = _make_note(tmp_path, UNBOUNDED_NOTE)
        update_section(note, "summary", "Content.")
        text = note.read_text()
        assert "<!-- wvb:section:summary -->" in text
        assert "<!-- /wvb:section:summary -->" in text


class TestAppendSection:
    def test_appends_inside_existing_boundaries(self, tmp_path):
        note = _make_note(tmp_path, BOUNDED_NOTE)
        append_section(note, "summary", "Extra line.")
        text = note.read_text()
        assert "Original content." in text
        assert "Extra line." in text

    def test_creates_boundaries_when_missing(self, tmp_path):
        note = _make_note(tmp_path, UNBOUNDED_NOTE)
        append_section(note, "new-section", "Brand new.")
        text = note.read_text()
        assert "Brand new." in text
        assert "<!-- wvb:section:new-section -->" in text

    def test_no_duplication_on_rerun(self, tmp_path):
        note = _make_note(tmp_path, BOUNDED_NOTE)
        append_section(note, "summary", "Unique line.")
        append_section(note, "summary", "Unique line.")  # second call
        text = note.read_text()
        assert text.count("Unique line.") == 1

    def test_original_content_preserved(self, tmp_path):
        note = _make_note(tmp_path, UNBOUNDED_NOTE)
        append_section(note, "summary", "New stuff.")
        text = note.read_text()
        assert "No section markers here." in text


class TestUpdateFrontmatter:
    def test_merges_new_key(self, tmp_path):
        note = _make_note(
            tmp_path,
            "---\ntitle: Old Title\n---\n# Body\n",
        )
        update_frontmatter(note, {"status": "filming"})
        from workshop_video_brain.production_brain.notes.frontmatter import parse_note
        fm, _ = parse_note(note)
        assert fm["status"] == "filming"
        assert fm["title"] == "Old Title"  # preserved

    def test_updates_existing_key(self, tmp_path):
        note = _make_note(
            tmp_path,
            "---\ntitle: Old Title\nstatus: idea\n---\n# Body\n",
        )
        update_frontmatter(note, {"status": "published"})
        from workshop_video_brain.production_brain.notes.frontmatter import parse_note
        fm, _ = parse_note(note)
        assert fm["status"] == "published"

    def test_does_not_clobber_unrelated_keys(self, tmp_path):
        note = _make_note(
            tmp_path,
            "---\ntitle: T\ntags: [a, b]\ncustom: keep-me\n---\n# Body\n",
        )
        update_frontmatter(note, {"status": "review"})
        from workshop_video_brain.production_brain.notes.frontmatter import parse_note
        fm, _ = parse_note(note)
        assert fm["tags"] == ["a", "b"]
        assert fm["custom"] == "keep-me"
