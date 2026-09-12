"""Where the shipped template trees are found at runtime -- stated once.

``<repo>/templates/`` holds three trees, each read by a different part of the
package:

===============  ==========================================================
``render``       YAML render profiles (``edit_mcp.adapters.render.profiles``)
``obsidian``     Jinja2 note templates (``production_brain.notes.writer``)
``titles``       YAML title-card styles (``edit_mcp.server.bundles.titles``
                 and ``edit_mcp.pipelines.review_loop``)
===============  ==========================================================

All three live **outside** the package directory, so there are two places a
tree can be, and which one wins matters:

* **Installed from a wheel.** There is no repository. The templates are shipped
  inside the package, at ``workshop_video_brain/templates/<tree>/`` -- the wheel
  build copies them there (``[tool.hatch.build.targets.wheel.force-include]`` in
  **both** ``pyproject.toml`` files, since either build root can produce the
  wheel a user installs).
* **Run from a source checkout.** The package directory has no ``templates/``;
  the repository root, four levels up from this file, does. That is the copy a
  developer edits, and it must keep winning in a checkout so an edit takes
  effect without a rebuild.

Why this module exists rather than the rule being repeated per loader: it *was*
repeated, three times, and the copies disagreed. ``bundles/titles`` and
``pipelines/review_loop`` each carried a parent-walk ending in a
``parents[5] / "templates" / "titles"`` fallback -- but the two modules sit at
different depths, so those two "conventional locations" were different
directories, and from a wheel install (where the walk finds nothing and the
fallback is what you get) the two loaders resolved two different absent paths.
The render loader carried a third, correct, statement of the same rule. One
statement is the point.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# ``.../workshop_video_brain/core/template_paths.py`` -> the package directory.
# This is the candidate that survives a wheel install, because it is relative to
# the package rather than to a repository that is not there.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# ``<repo>/`` -- the package lives at
# ``<repo>/workshop-video-brain/src/workshop_video_brain``, so four more levels.
_REPO_ROOT = Path(__file__).resolve().parents[4]


def first_existing(candidates: Iterable[Path], fallback: Path) -> Path:
    """The first candidate that is a directory, else *fallback*.

    The fallback is returned rather than ``None`` so a lookup that finds nothing
    still has a concrete path to name in its error message.
    """
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return fallback


def packaged_template_dir(tree: str) -> Path:
    """The copy shipped inside the installed package."""
    return _PACKAGE_ROOT / "templates" / tree


def repo_template_dir(tree: str) -> Path:
    """The editable copy at ``<repo>/templates/<tree>``."""
    return _REPO_ROOT / "templates" / tree


def template_dir(tree: str) -> Path:
    """The directory *tree*'s templates are read from.

    Packaged copy first (a wheel install has no repository), repository copy
    second (a checkout must see edits without a rebuild). Resolved on every call
    rather than at import, so a test or a build step that creates one of them
    afterwards is still seen.
    """
    return first_existing(
        (packaged_template_dir(tree), repo_template_dir(tree)),
        repo_template_dir(tree),
    )
