"""Note writer: create Obsidian notes from Jinja2 templates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .frontmatter import write_note

# Default templates directory relative to the package root
_DEFAULT_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent.parent.parent.parent
    / "templates"
    / "obsidian"
)


class NoteWriter:
    """Create Obsidian notes from Jinja2 templates."""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        templates_dir = Path(templates_dir) if templates_dir else _DEFAULT_TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape([]),
            keep_trailing_newline=True,
        )

    def create(
        self,
        vault_path: Path | str,
        folder: str,
        filename: str,
        template_name: str,
        frontmatter: dict[str, Any] | None = None,
        sections: dict[str, str] | None = None,
    ) -> Path:
        """Create a new note.  Raises FileExistsError if the file already exists.

        Args:
            vault_path: Root of the Obsidian vault.
            folder: Sub-folder inside the vault (created if missing).
            filename: Note filename, e.g. ``my-note.md``.
            template_name: Template filename, e.g. ``video-idea.md``.
            frontmatter: Extra frontmatter values to pass to the template and
                         embed in the note header.
            sections: Dict of section name -> content to inject into the
                      rendered template.

        Returns:
            The Path of the created note.
        """
        note_path = Path(vault_path) / folder / filename
        if note_path.exists():
            raise FileExistsError(f"Note already exists: {note_path}")

        template = self._env.get_template(template_name)
        context: dict[str, Any] = {
            "frontmatter": frontmatter or {},
            "sections": sections or {},
        }
        if frontmatter:
            context.update(frontmatter)
        body = template.render(**context)

        # Strip YAML front-matter from the rendered template body if present,
        # then delegate to write_note so frontmatter is normalised.
        import re
        fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        match = fm_re.match(body)
        import yaml as _yaml
        if match:
            template_fm = _yaml.safe_load(match.group(1)) or {}
            body_only = body[match.end():]
        else:
            template_fm = {}
            body_only = body

        # Merge: template fm first, caller-supplied fm wins
        merged_fm: dict[str, Any] = {**template_fm, **(frontmatter or {})}

        write_note(note_path, merged_fm, body_only)
        return note_path
