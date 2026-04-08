"""Render profile loading and validation.

Profiles are defined in templates/render/*.yaml relative to the package root.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from workshop_video_brain.core.models._base import SerializableMixin

# Default profiles directory
_DEFAULT_PROFILES_DIR = (
    Path(__file__).parent.parent.parent.parent.parent.parent.parent
    / "templates"
    / "render"
)


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
    dir_path = Path(profiles_dir) if profiles_dir else _DEFAULT_PROFILES_DIR
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
    dir_path = Path(profiles_dir) if profiles_dir else _DEFAULT_PROFILES_DIR

    if not dir_path.exists():
        return []

    return sorted(
        p.stem for p in dir_path.glob("*.yaml")
        if p.is_file()
    )
