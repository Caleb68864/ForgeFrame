"""Every shipped template tree must be findable from an installed wheel.

``<repo>/templates/`` holds three trees -- ``render`` (YAML render profiles),
``obsidian`` (Jinja2 note templates) and ``titles`` (YAML title-card styles) --
and all three live **outside** the package directory. ``templates/render`` was
packaged first (see ``test_render_profiles_packaging``); the other two were not,
so from a wheel install ``NoteWriter()`` saw zero note templates and both title
loaders saw zero styles, while the README, the tool docstrings and the handbook
promised all of them.

Measured on real wheels rather than argued -- built from **both** build roots,
installed into throwaway venvs and loaded through the installed package with no
checkout on ``sys.path``; that run is recorded in ``docs/decisions.md`` and
cannot be re-run in the unit tier (it needs a build backend and a network).
What is checked here is everything that run depends on:

* the resolution rule -- packaged copy first, repository copy second -- stated
  **once**, in ``core.template_paths``, and used by every loader.  There used to
  be three separate statements of it: two independent parent-walks (one in
  ``bundles/titles``, one in ``pipelines/review_loop``) whose "conventional
  location" fallbacks pointed at *different* directories because the two modules
  sit at different depths, plus one explicit two-candidate rule in the render
  loader.  A rule written three times is a rule that can disagree with itself,
  and this one did.
* that the packaged candidate points **inside** the package, which is the whole
  reason it survives an install;
* that **both** build roots copy **every** tree into the package, since either
  can produce the wheel a user installs;
* that each template the code names by literal is actually in its tree.  This is
  what caught ``visual-research-index.md``: the only copy lived under the plugin
  directory, where no loader looks, so the visual-research Obsidian export
  raised ``TemplateNotFound`` from a plain source checkout.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from workshop_video_brain.core import template_paths as TP

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every tree under ``<repo>/templates``.  Adding a directory there without
#: adding it here (and to both pyprojects) is the defect this file exists for.
TREES = ("obsidian", "render", "titles")

_PYPROJECTS = {
    # label -> (pyproject path, the prefix a force-include source needs)
    "repository root": (_REPO_ROOT / "pyproject.toml", ""),
    "plugin directory": (_REPO_ROOT / "workshop-video-brain" / "pyproject.toml", "../"),
}

#: Template filenames the code names as string literals.  Each must exist in its
#: tree or the code that names it raises at runtime.
DOCUMENTED_TEMPLATES = {
    # production_brain.notes.writer callers
    "obsidian": [
        "video-idea.md",
        "shot-plan.md",
        "transcript.md",
        "edit-review.md",
        "publish-checklist.md",
        "in-progress.md",
        # edit_mcp.pipelines.visual_research.export._OBSIDIAN_TEMPLATE
        "visual-research-index.md",
    ],
    # bundles/titles.title_card_add default + docstring, review_loop default
    "titles": ["lower-third.yaml", "chapter-card.yaml", "thumbnail.yaml"],
    # the five the README/docstrings promise (the other seven are pinned by
    # test_render_profiles_packaging)
    "render": [
        "youtube-1080p.yaml",
        "youtube-4k.yaml",
        "vimeo-hq.yaml",
        "master-prores.yaml",
        "master-dnxhr.yaml",
    ],
}


# ---------------------------------------------------------------------------
# The resolution rule, stated once, in both directions
# ---------------------------------------------------------------------------


def test_the_first_existing_candidate_wins(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    assert TP.first_existing((first, second), tmp_path) == first


def test_a_missing_candidate_is_skipped_rather_than_returned(tmp_path: Path) -> None:
    present = tmp_path / "present"
    present.mkdir()
    assert TP.first_existing((tmp_path / "gone", present), tmp_path) == present


def test_a_file_does_not_count_as_a_candidate_directory(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy"
    decoy.write_text("not a directory", encoding="utf-8")
    real = tmp_path / "real"
    real.mkdir()
    assert TP.first_existing((decoy, real), tmp_path) == real


def test_the_fallback_is_returned_when_nothing_exists(tmp_path: Path) -> None:
    """So a failed lookup still has a concrete path to name in its error."""
    fallback = tmp_path / "fallback"
    assert TP.first_existing((tmp_path / "a", tmp_path / "b"), fallback) == fallback


@pytest.mark.parametrize("tree", TREES)
def test_the_packaged_candidate_is_inside_the_package(tree: str) -> None:
    """This is the whole fix: a path relative to the installed package survives
    a wheel install, a path relative to the repository does not."""
    package_root = Path(TP.__file__).resolve().parents[1]
    assert package_root.name == "workshop_video_brain"
    assert TP.packaged_template_dir(tree) == package_root / "templates" / tree


_IMPORTED_FROM_CHECKOUT = Path(TP.__file__).resolve().is_relative_to(_REPO_ROOT)
_needs_checkout = pytest.mark.skipif(
    not _IMPORTED_FROM_CHECKOUT,
    reason=(
        "asserts the repository-relative candidate; only meaningful when the "
        "package under test is the checkout rather than an installed copy"
    ),
)


@_needs_checkout
@pytest.mark.parametrize("tree", TREES)
def test_the_repository_candidate_is_the_editable_copy(tree: str) -> None:
    assert TP.repo_template_dir(tree) == _REPO_ROOT / "templates" / tree
    assert TP.repo_template_dir(tree).is_dir()


@pytest.mark.parametrize("tree", TREES)
def test_the_packaged_copy_is_preferred_over_the_repository_copy(
    tree: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "packaged"
    repo = tmp_path / "repo"
    (packaged / "templates" / tree).mkdir(parents=True)
    (repo / "templates" / tree).mkdir(parents=True)
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", packaged)
    monkeypatch.setattr(TP, "_REPO_ROOT", repo)
    assert TP.template_dir(tree) == packaged / "templates" / tree


@pytest.mark.parametrize("tree", TREES)
def test_the_repository_copy_is_used_when_nothing_is_packaged(
    tree: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept control: a source checkout has no packaged copy, and an edit to
    the repository template must take effect without a rebuild."""
    packaged = tmp_path / "packaged"
    repo = tmp_path / "repo"
    packaged.mkdir()
    (repo / "templates" / tree).mkdir(parents=True)
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", packaged)
    monkeypatch.setattr(TP, "_REPO_ROOT", repo)
    assert TP.template_dir(tree) == repo / "templates" / tree


@pytest.mark.parametrize("tree", TREES)
def test_the_resolved_directory_here_is_not_empty(tree: str) -> None:
    """Accept control, unmonkeypatched: whichever candidate wins in the tree the
    tests run from, it is one that actually has templates in it."""
    resolved = TP.template_dir(tree)
    assert resolved.is_dir(), resolved
    assert any(resolved.iterdir()), f"{tree}: resolved to an empty {resolved}"


# ---------------------------------------------------------------------------
# One rule, not three: every loader reads the shared resolver
# ---------------------------------------------------------------------------


def test_the_two_title_loaders_resolve_the_same_directory() -> None:
    from workshop_video_brain.edit_mcp.pipelines import review_loop
    from workshop_video_brain.edit_mcp.server.bundles import titles

    assert titles._titles_template_dir() == TP.template_dir("titles")
    assert review_loop._titles_template_dir() == TP.template_dir("titles")


def test_the_two_title_loaders_agree_when_no_candidate_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install shape, which is the only one where the two disagreed.

    ``bundles/titles`` and ``pipelines/review_loop`` each used to carry their own
    parent-walk ending in ``parents[5] / "templates" / "titles"``.  In a checkout
    the walk finds the repository copy and both agree, so the disagreement is
    invisible here.  From a wheel install nothing exists on the walk and the
    fallback is what you get -- and the two modules sit at different depths, so
    the two fallbacks were different absent directories.  Measured on a real
    install: ``<venv>/lib/python3.14/templates/titles`` for one loader and
    ``<venv>/lib/templates/titles`` for the other."""
    from workshop_video_brain.edit_mcp.pipelines import review_loop
    from workshop_video_brain.edit_mcp.server.bundles import titles

    nowhere = tmp_path / "nowhere"
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", nowhere)
    monkeypatch.setattr(TP, "_REPO_ROOT", nowhere)

    assert titles._titles_template_dir() == review_loop._titles_template_dir()
    assert titles._titles_template_dir() == TP.template_dir("titles")


def test_the_note_writer_default_follows_the_shared_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workshop_video_brain.production_brain.notes.writer import NoteWriter

    packaged = tmp_path / "packaged"
    (packaged / "templates" / "obsidian").mkdir(parents=True)
    (packaged / "templates" / "obsidian" / "only-here.md").write_text(
        "hi", encoding="utf-8"
    )
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", packaged)
    assert sorted(NoteWriter()._env.list_templates()) == ["only-here.md"]


def test_an_explicit_templates_dir_still_overrides_the_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept control: the resolution rule must not swallow a caller's own
    ``templates_dir`` argument."""
    from workshop_video_brain.production_brain.notes.writer import NoteWriter

    packaged = tmp_path / "packaged"
    (packaged / "templates" / "obsidian").mkdir(parents=True)
    (packaged / "templates" / "obsidian" / "shadowed.md").write_text(
        "no", encoding="utf-8"
    )
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", packaged)

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / "chosen.md").write_text("yes", encoding="utf-8")
    assert sorted(NoteWriter(templates_dir=explicit)._env.list_templates()) == [
        "chosen.md"
    ]


def test_the_title_loaders_follow_the_shared_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workshop_video_brain.edit_mcp.pipelines import review_loop
    from workshop_video_brain.edit_mcp.server.bundles import titles

    packaged = tmp_path / "packaged"
    tdir = packaged / "templates" / "titles"
    tdir.mkdir(parents=True)
    (tdir / "only-here.yaml").write_text("font_family: Probe\n", encoding="utf-8")
    monkeypatch.setattr(TP, "_PACKAGE_ROOT", packaged)

    assert titles._load_style("only-here") == {"font_family": "Probe"}
    assert review_loop.load_thumbnail_style("only-here") == {"font_family": "Probe"}


def test_the_render_loader_follows_the_shared_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The render tree was packaged first and keeps its own module-level
    candidates; they must be the shared rule's candidates, not a fourth copy."""
    from workshop_video_brain.edit_mcp.adapters.render import profiles

    assert profiles.profiles_dir() == TP.template_dir("render")
    assert profiles._PACKAGED_PROFILES_DIR == TP.packaged_template_dir("render")
    assert profiles._REPO_PROFILES_DIR == TP.repo_template_dir("render")
    assert profiles._first_existing is TP.first_existing


# ---------------------------------------------------------------------------
# Both build roots ship every tree into the package
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(_PYPROJECTS))
@pytest.mark.parametrize("tree", TREES)
def test_the_wheel_build_copies_every_tree_into_the_package(
    tree: str, label: str
) -> None:
    pyproject, prefix = _PYPROJECTS[label]
    source = f"{prefix}templates/{tree}"
    destination = f"workshop_video_brain/templates/{tree}"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    include = (
        config.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("force-include", {})
    )
    assert include.get(source) == destination, (
        f"{label}: the wheel must copy {source!r} to {destination!r}, or an "
        f"install of that wheel finds no {tree} templates. Got {include!r}."
    )
    assert (pyproject.parent / source).is_dir(), (
        f"{label}: force-include source {source!r} does not exist relative to "
        f"{pyproject.parent}"
    )


@pytest.mark.parametrize("label", sorted(_PYPROJECTS))
def test_no_template_tree_is_left_out_of_a_build_root(label: str) -> None:
    """The list above is only worth anything if it is the whole list: a new
    directory under ``<repo>/templates`` must be packaged, not forgotten."""
    on_disk = sorted(
        p.name for p in (_REPO_ROOT / "templates").iterdir() if p.is_dir()
    )
    assert on_disk == sorted(TREES), (
        "templates/ gained or lost a tree; add it to TREES and to the "
        f"force-include block of both pyprojects. On disk: {on_disk}"
    )
    pyproject, prefix = _PYPROJECTS[label]
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    include = (
        config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    )
    assert sorted(include) == sorted(f"{prefix}templates/{t}" for t in TREES)


# ---------------------------------------------------------------------------
# The templates the code names by literal are really there
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tree", "filename"),
    [(tree, name) for tree in TREES for name in DOCUMENTED_TEMPLATES[tree]],
)
def test_every_documented_template_is_in_its_tree(tree: str, filename: str) -> None:
    assert (_REPO_ROOT / "templates" / tree / filename).is_file()


def test_the_visual_research_export_can_load_its_own_template(tmp_path: Path) -> None:
    """Accept control through the real loader, not the file system: the export
    names ``visual-research-index.md`` and the only copy used to live under the
    plugin directory, where ``NoteWriter`` never looks.  The unit test for the
    export monkeypatched ``NoteWriter.__init__`` to point at its own inline copy
    of the template, so it could not see that."""
    from workshop_video_brain.edit_mcp.pipelines.visual_research import export
    from workshop_video_brain.production_brain.notes.writer import NoteWriter

    note = NoteWriter().create(
        tmp_path,
        "Research",
        "probe.md",
        export._OBSIDIAN_TEMPLATE,
        frontmatter={"source": "probe", "manifest_id": "m1", "capture_count": 0},
        sections={"captures": "none"},
    )
    assert note.is_file()
    assert "probe" in note.read_text(encoding="utf-8")
