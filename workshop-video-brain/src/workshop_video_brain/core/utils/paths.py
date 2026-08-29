"""Path utilities: safe filenames, versioned paths, workspace-relative helpers."""
from __future__ import annotations

import re
from pathlib import Path


def safe_filename(name: str) -> str:
    """Strip illegal filename characters and truncate to 200 chars.

    Removes ``<>:"/\\|?*``, replaces spaces with hyphens.
    """
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = cleaned.replace(" ", "-")
    return cleaned[:200]


def versioned_path(base: Path | str, extension: str) -> Path:
    """Return *base.extension* if it does not exist, otherwise *base-1.extension*, etc."""
    base = Path(base)
    candidate = base.with_suffix(extension)
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = base.with_name(f"{base.name}-{counter}").with_suffix(extension)
        if not candidate.exists():
            return candidate
        counter += 1


def workspace_relative(absolute: Path | str, workspace_root: Path | str) -> str:
    """Return *absolute* as a string relative to *workspace_root*."""
    return str(Path(absolute).relative_to(Path(workspace_root)))


# Workspace trees that tools must never write into (CLAUDE.md safety rules):
# ``media/raw/`` holds the user's only copy of their footage and
# ``projects/source/`` the untouched original projects. Matched on path
# *segments* (``.../media/raw/...``), not substrings, so a folder named
# ``raw_footage`` or ``my_media/raw`` elsewhere is not caught by accident.
PROTECTED_TREES: tuple[tuple[str, str], ...] = (("media", "raw"), ("projects", "source"))


class ProtectedPathError(ValueError):
    """A write was attempted inside a protected workspace tree."""


def is_protected_path(path: Path | str) -> bool:
    """True when *path* lies inside ``media/raw/`` or ``projects/source/``.

    Resolves symlinks/``..`` first so ``working_copies/../source/x.kdenlive``
    is caught. Purely lexical after that: the path need not exist.
    """
    try:
        parts = Path(path).resolve().parts
    except OSError:
        parts = Path(path).absolute().parts
    return any(
        parts[i] == a and parts[i + 1] == b
        for a, b in PROTECTED_TREES
        for i in range(len(parts) - 1)
    )


def assert_not_protected(path: Path | str, what: str = "output") -> Path:
    """Return *path* as a ``Path``, or raise :class:`ProtectedPathError`.

    The single guard behind the "never overwrite media/raw or
    projects/source" rule; the project serializer and the ffmpeg runner call
    it at their write sites so every tool inherits the rule.
    """
    p = Path(path)
    if is_protected_path(p):
        raise ProtectedPathError(
            f"Refusing to write {what} inside a protected tree "
            f"(media/raw or projects/source): {p}"
        )
    return p


def ensure_dir(path: Path | str) -> Path:
    """Create *path* and all parents; return the Path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
