"""The shipped render profiles must be findable from an installed wheel.

The five documented profiles are edited at ``<repo>/templates/render``, which is
**outside** the package directory. The loader resolved only that repository
path, so a wheel install -- which has no repository -- found nothing:
``list_profiles()`` returned ``[]`` and every documented name raised
``FileNotFoundError``.

The proof that this is fixed is a real wheel, built and installed into a
throwaway venv and loaded through the installed package; that run is recorded in
``docs/decisions.md`` and cannot be re-run cheaply in the unit tier (it needs a
build backend and a network-isolated build env). What *is* checked here is
everything that run depends on, so neither half can rot unnoticed:

* the resolution rule -- packaged copy first, repository copy second -- in both
  directions, and that both public entry points read the same directory;
* that the packaged candidate points **inside** the package rather than beside
  it, which is what makes it survive a wheel install at all;
* that both build roots actually copy the YAML into the package, since either
  can produce the wheel a user installs.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.render import profiles as P

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECTS = {
    "repository root": (_REPO_ROOT / "pyproject.toml", "templates/render"),
    "plugin directory": (
        _REPO_ROOT / "workshop-video-brain" / "pyproject.toml",
        "../templates/render",
    ),
}
_PACKAGE_DESTINATION = "workshop_video_brain/templates/render"

DOCUMENTED_PROFILES = [
    "youtube-1080p",
    "youtube-4k",
    "vimeo-hq",
    "master-prores",
    "master-dnxhr",
]


# ---------------------------------------------------------------------------
# The resolution rule, both directions
# ---------------------------------------------------------------------------


def test_the_first_existing_candidate_wins(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    assert P._first_existing((first, second), tmp_path) == first


def test_a_missing_candidate_is_skipped_rather_than_returned(tmp_path: Path) -> None:
    missing = tmp_path / "not-there"
    present = tmp_path / "present"
    present.mkdir()
    assert P._first_existing((missing, present), tmp_path) == present


def test_the_fallback_is_returned_when_nothing_exists(tmp_path: Path) -> None:
    """So a failed lookup still has a concrete path to name in its error."""
    fallback = tmp_path / "fallback"
    assert P._first_existing((tmp_path / "a", tmp_path / "b"), fallback) == fallback


def test_a_file_does_not_count_as_a_candidate_directory(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy"
    decoy.write_text("not a directory", encoding="utf-8")
    real = tmp_path / "real"
    real.mkdir()
    assert P._first_existing((decoy, real), tmp_path) == real


# ---------------------------------------------------------------------------
# The two candidates are the right two
# ---------------------------------------------------------------------------


def test_the_packaged_candidate_is_inside_the_package() -> None:
    """This is the whole fix: a path relative to the installed package survives
    a wheel install, a path relative to the repository does not."""
    package_root = Path(P.__file__).resolve().parents[3]
    assert package_root.name == "workshop_video_brain"
    assert P._PACKAGED_PROFILES_DIR == package_root / "templates" / "render"


_IMPORTED_FROM_CHECKOUT = Path(P.__file__).resolve().is_relative_to(_REPO_ROOT)
_needs_checkout = pytest.mark.skipif(
    not _IMPORTED_FROM_CHECKOUT,
    reason=(
        "asserts the repository-relative candidate; only meaningful when the "
        "package under test is the checkout rather than an installed copy"
    ),
)


@_needs_checkout
def test_the_repository_candidate_is_the_editable_copy() -> None:
    assert P._REPO_PROFILES_DIR == _REPO_ROOT / "templates" / "render"
    assert P._REPO_PROFILES_DIR.is_dir()


def test_the_packaged_copy_is_preferred_over_the_repository_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "packaged"
    repo = tmp_path / "repo"
    packaged.mkdir()
    repo.mkdir()
    monkeypatch.setattr(P, "_PACKAGED_PROFILES_DIR", packaged)
    monkeypatch.setattr(P, "_REPO_PROFILES_DIR", repo)
    assert P.profiles_dir() == packaged


def test_the_repository_copy_is_used_when_nothing_is_packaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept control: a source checkout has no packaged copy, and an edit to
    the repository YAML must still take effect without a rebuild."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(P, "_PACKAGED_PROFILES_DIR", tmp_path / "absent")
    monkeypatch.setattr(P, "_REPO_PROFILES_DIR", repo)
    assert P.profiles_dir() == repo


def test_the_resolved_directory_here_holds_every_documented_profile() -> None:
    """Accept control, unmonkeypatched: whichever candidate wins in the tree the
    tests run from, it is one that actually has the profiles in it."""
    resolved = P.profiles_dir()
    assert resolved.is_dir(), resolved
    names = {p.stem for p in resolved.glob("*.yaml")}
    assert set(DOCUMENTED_PROFILES) <= names, sorted(set(DOCUMENTED_PROFILES) - names)


@_needs_checkout
def test_this_checkout_resolves_to_the_repository_copy() -> None:
    """A source checkout has no packaged copy, so the repository one wins and an
    edit to the YAML takes effect without a rebuild."""
    assert not P._PACKAGED_PROFILES_DIR.exists()
    assert P.profiles_dir() == _REPO_ROOT / "templates" / "render"


# ---------------------------------------------------------------------------
# Both entry points read the same directory -- stated once, run through both
# ---------------------------------------------------------------------------


def test_both_entry_points_follow_the_resolved_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    (packaged / "only-here.yaml").write_text("name: only-here\n", encoding="utf-8")
    monkeypatch.setattr(P, "_PACKAGED_PROFILES_DIR", packaged)

    assert P.list_profiles() == ["only-here"]
    assert P.load_profile("only-here").name == "only-here"


def test_an_explicit_directory_still_overrides_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accept control: the resolution rule must not swallow the caller's own
    ``profiles_dir`` argument."""
    packaged = tmp_path / "packaged"
    packaged.mkdir()
    (packaged / "shadowed.yaml").write_text("name: shadowed\n", encoding="utf-8")
    monkeypatch.setattr(P, "_PACKAGED_PROFILES_DIR", packaged)

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / "chosen.yaml").write_text("name: chosen\n", encoding="utf-8")

    assert P.list_profiles(explicit) == ["chosen"]
    assert P.load_profile("chosen", explicit).name == "chosen"


# ---------------------------------------------------------------------------
# Both build roots ship the YAML into the package
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(_PYPROJECTS))
def test_the_wheel_build_copies_the_profiles_into_the_package(label: str) -> None:
    pyproject, source = _PYPROJECTS[label]
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    include = (
        config.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("force-include", {})
    )
    assert include.get(source) == _PACKAGE_DESTINATION, (
        f"{label}: the wheel must copy {source!r} to {_PACKAGE_DESTINATION!r}, "
        f"or an install of that wheel finds no render profiles. Got {include!r}."
    )
    assert (pyproject.parent / source).is_dir(), (
        f"{label}: force-include source {source!r} does not exist relative to "
        f"{pyproject.parent}"
    )


@pytest.mark.parametrize("name", DOCUMENTED_PROFILES)
def test_every_documented_profile_is_in_the_copied_directory(name: str) -> None:
    """The mapping above is only worth anything if the five names are in it."""
    assert (_REPO_ROOT / "templates" / "render" / f"{name}.yaml").is_file()
