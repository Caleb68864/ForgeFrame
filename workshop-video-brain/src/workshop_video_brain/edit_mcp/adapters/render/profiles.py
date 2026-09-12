"""Render profile loading and validation.

Profiles are YAML files, edited in the repository at ``<repo>/templates/render/``
-- the same tree the Obsidian and title-card loaders read. That is the only
render-profile source directory: a YAML placed anywhere else is invisible to
every tool (``tests/unit/test_render_profiles_expanded.py`` guards this).

Where they are *found at runtime* is a different question, and it has two
answers, because there are two ways this package gets onto a machine:

* **Installed from a wheel.** There is no repository. The YAML is shipped inside
  the package, at ``workshop_video_brain/templates/render/`` -- the wheel build
  copies ``templates/render`` there (``[tool.hatch.build.targets.wheel.
  force-include]`` in both ``pyproject.toml`` files, so a wheel built from
  either the repository root or the plugin directory carries them).
* **Run from a source checkout.** The package directory has no ``templates/``;
  the repository root, seven levels up from this file, does. That is the copy a
  developer edits, and it must keep winning in a checkout so an edit takes
  effect without a rebuild.

:func:`profiles_dir` states that precedence once -- packaged first, repository
second -- and every default-path lookup in this module goes through it. Before
this, only the repository path existed, so a wheel install found **no** profiles
at all: ``list_profiles()`` returned ``[]`` and every one of the five documented
profiles raised ``FileNotFoundError``.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from workshop_video_brain.core.models._base import SerializableMixin
from workshop_video_brain.core.template_paths import (
    first_existing as _first_existing,
    packaged_template_dir,
    repo_template_dir,
)

# The two candidates, named here so a test can monkeypatch either one. They are
# the shared rule's candidates (``core.template_paths``), which the Obsidian and
# title-card trees resolve through as well -- one statement, three trees.
#
# Shipped inside the installed package: .../workshop_video_brain/templates/render
_PACKAGED_PROFILES_DIR = packaged_template_dir("render")
# The repository's editable copy: <repo>/templates/render.
_REPO_PROFILES_DIR = repo_template_dir("render")


def profiles_dir() -> Path:
    """The directory the render profiles are read from.

    Packaged copy first (a wheel install has no repository), repository copy
    second (a checkout must see edits without a rebuild). Resolved on every call
    rather than at import, so a test or a build step that creates one of them
    afterwards is still seen.
    """
    return _first_existing(
        (_PACKAGED_PROFILES_DIR, _REPO_PROFILES_DIR), _REPO_PROFILES_DIR
    )


def _resolve_dir(profiles_dir_override: Path | str | None) -> Path:
    """One statement of "which directory does this call read?" for both
    :func:`load_profile` and :func:`list_profiles`."""
    if profiles_dir_override:
        return Path(profiles_dir_override)
    return profiles_dir()


class RenderProfile(SerializableMixin):
    """A render configuration profile loaded from YAML."""

    name: str
    width: int = 1920
    height: int = 1080
    fps: float = 25.0
    video_codec: str = "libx264"
    video_bitrate: str = "8M"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    extra_args: list[str] = Field(default_factory=list)
    fast_start: bool = False
    movflags: str | None = None
    # Alpha / advanced melt-consumer settings ------------------------------
    # pix_fmt: encoder pixel format (e.g. "yuva420p", "argb"); passed to both
    #   the melt avformat consumer and appended for ffmpeg fallback.
    pix_fmt: str | None = None
    # mlt_image_format: MLT internal image format. Must be "rgba" for alpha
    #   renders so the alpha channel survives the MLT pipeline instead of
    #   being flattened onto black.
    mlt_image_format: str | None = None
    # melt_args: extra raw "key=value" properties for the melt avformat
    #   consumer (e.g. "f=webm" to force container, "vprofile=4" for ProRes
    #   4444). Ignored by the ffmpeg fallback path.
    melt_args: list[str] = Field(default_factory=list)
    # container: output file extension without the dot (e.g. "webm", "mov",
    #   "mkv"). Drives the render output filename; defaults to mp4 when unset.
    container: str | None = None
    # disable_audio: emit no audio stream. Alpha containers (webm/mkv/mov)
    #   often pair badly with the default AAC audio codec, and cutout/logo
    #   exports rarely need audio.
    disable_audio: bool = False


def load_profile(
    name: str,
    profiles_dir: Path | str | None = None,
) -> RenderProfile:
    """Load a render profile by name from the profiles directory.

    Args:
        name: Profile name, e.g. "preview", "draft-youtube", "final-youtube".
        profiles_dir: Optional override for profiles directory.

    Returns:
        RenderProfile loaded from the corresponding YAML file.

    Raises:
        FileNotFoundError: If the profile YAML does not exist.
        ValueError: If the YAML is malformed or missing required fields.
    """
    dir_path = _resolve_dir(profiles_dir)
    profile_path = dir_path / f"{name}.yaml"

    if not profile_path.exists():
        raise FileNotFoundError(
            f"Render profile '{name}' not found at {profile_path}. "
            f"Available profiles: {list_profiles(profiles_dir)}"
        )

    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Render profile '{name}' is not a valid YAML dict.")

    try:
        return RenderProfile(**raw)
    except Exception as exc:
        raise ValueError(f"Invalid render profile '{name}': {exc}") from exc


def list_profiles(profiles_dir: Path | str | None = None) -> list[str]:
    """Return a sorted list of available profile names.

    Args:
        profiles_dir: Optional override for profiles directory.

    Returns:
        List of profile name strings (without .yaml extension).
    """
    dir_path = _resolve_dir(profiles_dir)

    if not dir_path.exists():
        return []

    return sorted(
        p.stem for p in dir_path.glob("*.yaml")
        if p.is_file()
    )
