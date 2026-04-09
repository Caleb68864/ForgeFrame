"""Unit tests for NoteWriter."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from workshop_video_brain.production_brain.notes.writer import NoteWriter

# Locate the templates directory so we can create a NoteWriter that points
# at the real templates used by the application.
_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent
    / "templates"
    / "obsidian"
)


@pytest.fixture
def writer() -> NoteWriter:
    """Return a NoteWriter pointed at the real obsidian templates."""
    return NoteWriter(templates_dir=_TEMPLATES_DIR)


class TestNoteWriterCreate:
    def test_creates_file_at_correct_path(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="test-note.md",
            template_name="video-idea.md",
        )
        assert note_path.exists()
        assert note_path == tmp_path / "videos" / "test-note.md"

    def test_creates_parent_directory_if_missing(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="deep/nested/folder",
            filename="note.md",
            template_name="video-idea.md",
        )
        assert note_path.exists()

    def test_raises_file_exists_error_on_duplicate(self, writer: NoteWriter, tmp_path: Path):
        writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="dup.md",
            template_name="video-idea.md",
        )
        with pytest.raises(FileExistsError):
            writer.create(
                vault_path=tmp_path,
                folder="videos",
                filename="dup.md",
                template_name="video-idea.md",
            )

    def test_note_has_yaml_frontmatter(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="fm-test.md",
            template_name="video-idea.md",
        )
        content = note_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        # There should be a closing ---
        assert "\n---\n" in content

    def test_frontmatter_values_stored(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="with-fm.md",
            template_name="video-idea.md",
            frontmatter={"title": "My Test Video", "status": "idea"},
        )
        content = note_path.read_text(encoding="utf-8")
        # Parse frontmatter
        end = content.index("\n---\n", 4)
        fm = yaml.safe_load(content[4:end])
        assert fm["title"] == "My Test Video"
        assert fm["status"] == "idea"

    def test_body_contains_template_sections(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="videos",
            filename="sections.md",
            template_name="video-idea.md",
        )
        content = note_path.read_text(encoding="utf-8")
        # video-idea.md template has a Hook section
        assert "Hook" in content

    def test_returns_path_object(self, writer: NoteWriter, tmp_path: Path):
        note_path = writer.create(
            vault_path=tmp_path,
            folder="out",
            filename="typed.md",
            template_name="video-idea.md",
        )
        assert isinstance(note_path, Path)
