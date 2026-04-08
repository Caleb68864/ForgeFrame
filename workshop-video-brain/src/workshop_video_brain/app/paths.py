"""Path resolution utilities for workshop-video-brain."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.app.config import Config


def resolve_workspace_path(config: Config) -> Path:
    """Return the resolved workspace root as a Path.

    Falls back to the current working directory when WVB_WORKSPACE_ROOT is not set.
    """
    if config.workspace_root:
        return Path(config.workspace_root).expanduser().resolve()
    return Path.cwd()
