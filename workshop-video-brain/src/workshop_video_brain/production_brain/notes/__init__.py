"""Obsidian note utilities: frontmatter, writer, updater."""
from .frontmatter import merge_frontmatter, parse_note, write_note
from .updater import append_section, update_frontmatter, update_section
from .writer import NoteWriter

__all__ = [
    "parse_note",
    "write_note",
    "merge_frontmatter",
    "update_frontmatter",
    "update_section",
    "append_section",
    "NoteWriter",
]
