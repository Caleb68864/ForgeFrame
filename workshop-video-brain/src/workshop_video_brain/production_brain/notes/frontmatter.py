"""Obsidian frontmatter parsing, writing, and merging."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_note(path: Path | str) -> tuple[dict, str]:
    """Parse an Obsidian note into frontmatter dict and body string.

    Returns:
        (frontmatter_dict, body_string) -- frontmatter is empty dict when absent.
    """
    text = Path(path).read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match:
        fm = yaml.safe_load(match.group(1)) or {}
        body = text[match.end():]
        return fm, body
    return {}, text


def write_note(path: Path | str, frontmatter: dict, body: str) -> None:
    """Write *frontmatter* (as YAML) + *body* (markdown) to *path*.

    Creates parent directories if needed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_yaml}---\n{body}"
    path.write_text(content, encoding="utf-8")


def merge_frontmatter(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *updates* into *existing*.

    - Updates win on scalar conflicts.
    - Nested dicts are recursively merged.
    - Lists from *updates* replace lists in *existing*.
    - Keys in *existing* that are absent from *updates* are preserved.
    """
    result = dict(existing)
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_frontmatter(result[key], value)
        else:
            result[key] = value
    return result
