"""Note updater: frontmatter merging and section-aware content updates."""
from __future__ import annotations

import re
from pathlib import Path

from .frontmatter import merge_frontmatter, parse_note, write_note

# Pattern for wvb section boundaries
_SECTION_RE = re.compile(
    r"<!-- wvb:section:(\w[\w-]*) -->(.*?)<!-- /wvb:section:\1 -->",
    re.DOTALL,
)


def update_frontmatter(note_path: Path | str, updates: dict) -> None:
    """Merge *updates* into the note's existing frontmatter without clobbering
    unrelated keys."""
    note_path = Path(note_path)
    fm, body = parse_note(note_path)
    merged = merge_frontmatter(fm, updates)
    write_note(note_path, merged, body)


def update_section(note_path: Path | str, section_name: str, content: str) -> None:
    """Replace the content between ``<!-- wvb:section:name -->`` boundaries.

    If the boundaries are not found the content is appended to the end of the
    file (never destructive).
    """
    note_path = Path(note_path)
    text = note_path.read_text(encoding="utf-8")

    open_tag = f"<!-- wvb:section:{section_name} -->"
    close_tag = f"<!-- /wvb:section:{section_name} -->"

    pattern = re.compile(
        re.escape(open_tag) + r"(.*?)" + re.escape(close_tag),
        re.DOTALL,
    )
    if pattern.search(text):
        new_text = pattern.sub(
            f"{open_tag}\n{content}\n{close_tag}",
            text,
        )
    else:
        # Append section boundaries at end of file
        separator = "\n" if text.endswith("\n") else "\n\n"
        new_text = text + separator + f"{open_tag}\n{content}\n{close_tag}\n"

    note_path.write_text(new_text, encoding="utf-8")


def append_section(note_path: Path | str, section_name: str, content: str) -> None:
    """Append *content* inside the named section boundaries.

    - If boundaries exist, content is appended inside them.
    - If they do not exist, the section block is appended to the end of the
      file.
    - Re-running with the same content does NOT duplicate it.
    """
    note_path = Path(note_path)
    text = note_path.read_text(encoding="utf-8")

    open_tag = f"<!-- wvb:section:{section_name} -->"
    close_tag = f"<!-- /wvb:section:{section_name} -->"

    pattern = re.compile(
        re.escape(open_tag) + r"(.*?)" + re.escape(close_tag),
        re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        existing_body = match.group(1)
        # Idempotency: skip if content already present
        if content.strip() in existing_body:
            return
        new_body = existing_body.rstrip("\n") + "\n" + content + "\n"
        new_text = text[: match.start()] + f"{open_tag}{new_body}{close_tag}" + text[match.end():]
    else:
        # Idempotency: skip if content appears right before an implicit block
        if content.strip() in text:
            # still append the section wrapper if the boundaries are missing
            pass
        separator = "\n" if text.endswith("\n") else "\n\n"
        new_text = text + separator + f"{open_tag}\n{content}\n{close_tag}\n"

    note_path.write_text(new_text, encoding="utf-8")
