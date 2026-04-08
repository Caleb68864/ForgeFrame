"""Integration tests: Obsidian note lifecycle.

Tests the full lifecycle:
  create → update frontmatter → append section → update bounded section
  → re-run (no duplication) → verify valid markdown.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from workshop_video_brain.production_brain.notes.frontmatter import parse_note, write_note
from workshop_video_brain.production_brain.notes.updater import (
    append_section,
    update_frontmatter,
    update_section,
)
from workshop_video_brain.production_brain.notes.writer import NoteWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "obsidian"


def _has_templates() -> bool:
    return _TEMPLATES_DIR.exists() and any(_TEMPLATES_DIR.glob("*.md"))


# ---------------------------------------------------------------------------
# Tests: create note
# ---------------------------------------------------------------------------


class TestNoteCreate:
    @pytest.mark.skipif(not _has_templates(), reason="Templates not available")
    def test_create_note_from_template(self, tmp_path):
        writer = NoteWriter(templates_dir=_TEMPLATES_DIR)
        note_path = writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="test-video.md",
            template_name="video-idea.md",
            frontmatter={"title": "Test Video", "status": "idea"},
        )
        assert note_path.exists()
        fm, body = parse_note(note_path)
        assert fm.get("title") == "Test Video"
        assert fm.get("status") == "idea"

    def test_create_note_without_template(self, tmp_path):
        note_path = tmp_path / "notes" / "direct.md"
        write_note(
            note_path,
            frontmatter={"title": "Direct Note", "tags": ["test"]},
            body="# Direct Note\n\nSome content here.\n",
        )
        assert note_path.exists()
        fm, body = parse_note(note_path)
        assert fm["title"] == "Direct Note"
        assert "test" in fm["tags"]

    @pytest.mark.skipif(not _has_templates(), reason="Templates not available")
    def test_create_raises_on_duplicate(self, tmp_path):
        writer = NoteWriter(templates_dir=_TEMPLATES_DIR)
        writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="dup-test.md",
            template_name="video-idea.md",
        )
        with pytest.raises(FileExistsError):
            writer.create(
                vault_path=tmp_path,
                folder="videos",
                filename="dup-test.md",
                template_name="video-idea.md",
            )


# ---------------------------------------------------------------------------
# Tests: update frontmatter
# ---------------------------------------------------------------------------


class TestUpdateFrontmatter:
    def _make_note(self, path: Path) -> Path:
        write_note(path, {"title": "My Note", "status": "idea", "tags": ["video"]}, "# Body\n")
        return path

    def test_updates_existing_key(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        update_frontmatter(note, {"status": "editing"})
        fm, _ = parse_note(note)
        assert fm["status"] == "editing"

    def test_preserves_untouched_keys(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        update_frontmatter(note, {"status": "editing"})
        fm, _ = parse_note(note)
        assert fm["title"] == "My Note"
        assert fm["tags"] == ["video"]

    def test_adds_new_key(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        update_frontmatter(note, {"workspace_root": "/tmp/workspace"})
        fm, _ = parse_note(note)
        assert fm["workspace_root"] == "/tmp/workspace"

    def test_deep_merge_nested_dict(self, tmp_path):
        note = tmp_path / "nested.md"
        write_note(note, {"meta": {"version": 1, "author": "alice"}}, "body\n")
        update_frontmatter(note, {"meta": {"version": 2}})
        fm, _ = parse_note(note)
        assert fm["meta"]["version"] == 2
        assert fm["meta"]["author"] == "alice"


# ---------------------------------------------------------------------------
# Tests: append section
# ---------------------------------------------------------------------------


class TestAppendSection:
    def _make_note(self, path: Path) -> Path:
        write_note(path, {"title": "Section Note"}, "# Body\n\nSome content.\n")
        return path

    def test_creates_section_if_absent(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        append_section(note, "notes", "First entry")
        content = note.read_text(encoding="utf-8")
        assert "<!-- wvb:section:notes -->" in content
        assert "First entry" in content

    def test_appends_to_existing_section(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        append_section(note, "notes", "Entry 1")
        append_section(note, "notes", "Entry 2")
        content = note.read_text(encoding="utf-8")
        assert "Entry 1" in content
        assert "Entry 2" in content

    def test_no_duplication_on_second_run(self, tmp_path):
        note = self._make_note(tmp_path / "note.md")
        append_section(note, "notes", "Unique entry")
        append_section(note, "notes", "Unique entry")  # second call, same content
        content = note.read_text(encoding="utf-8")
        assert content.count("Unique entry") == 1


# ---------------------------------------------------------------------------
# Tests: update (replace) section
# ---------------------------------------------------------------------------


class TestUpdateSection:
    def _make_note_with_section(self, path: Path) -> Path:
        body = (
            "# Body\n\n"
            "<!-- wvb:section:status -->\n"
            "old content\n"
            "<!-- /wvb:section:status -->\n"
        )
        write_note(path, {"title": "Section Note"}, body)
        return path

    def test_replaces_section_content(self, tmp_path):
        note = self._make_note_with_section(tmp_path / "note.md")
        update_section(note, "status", "new content")
        content = note.read_text(encoding="utf-8")
        assert "new content" in content
        assert "old content" not in content

    def test_creates_section_if_absent(self, tmp_path):
        note = tmp_path / "nosection.md"
        write_note(note, {"title": "No Section"}, "# Body\n")
        update_section(note, "tags", "some tags here")
        content = note.read_text(encoding="utf-8")
        assert "<!-- wvb:section:tags -->" in content
        assert "some tags here" in content

    def test_preserves_other_content(self, tmp_path):
        note = self._make_note_with_section(tmp_path / "note.md")
        update_section(note, "status", "updated")
        content = note.read_text(encoding="utf-8")
        assert "# Body" in content


# ---------------------------------------------------------------------------
# Tests: full lifecycle + valid markdown
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_lifecycle_note_is_valid_markdown(self, tmp_path):
        """Full lifecycle: create → update fm → append → update section → verify."""
        note = tmp_path / "lifecycle.md"

        # 1. Create
        write_note(note, {"title": "Lifecycle", "status": "idea"}, "# Lifecycle Note\n\n")

        # 2. Update frontmatter
        update_frontmatter(note, {"status": "editing", "workspace_root": "/tmp/ws"})

        # 3. Append section
        append_section(note, "progress", "Step 1 complete")
        append_section(note, "progress", "Step 2 complete")

        # 4. Update bounded section
        update_section(note, "render-log", "Preview rendered at 2024-01-01")

        # 5. Re-run with same content — no duplication
        append_section(note, "progress", "Step 1 complete")

        content = note.read_text(encoding="utf-8")

        # Verify frontmatter block
        assert content.startswith("---\n")
        assert "status: editing" in content

        # Verify sections
        assert content.count("Step 1 complete") == 1
        assert "Step 2 complete" in content
        assert "Preview rendered" in content

        # Verify well-formed section boundaries
        assert content.count("<!-- wvb:section:progress -->") == 1
        assert content.count("<!-- /wvb:section:progress -->") == 1
        assert content.count("<!-- wvb:section:render-log -->") == 1
        assert content.count("<!-- /wvb:section:render-log -->") == 1

        # Verify valid YAML frontmatter parseable
        fm, body = parse_note(note)
        assert fm["title"] == "Lifecycle"
        assert fm["status"] == "editing"
        assert "workspace_root" in fm
