"""Naming utilities: slugify, timestamp prefix."""
from __future__ import annotations

import re
from datetime import datetime


def slugify(text: str) -> str:
    """Convert *text* to a URL-safe slug (lowercase, hyphens, no special chars)."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def timestamp_prefix() -> str:
    """Return a timestamp string in YYYY-MM-DD-HHMMSS format."""
    return datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
