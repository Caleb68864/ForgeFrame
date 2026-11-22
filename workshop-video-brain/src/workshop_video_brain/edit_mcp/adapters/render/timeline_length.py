"""Timeline length of a ``.kdenlive`` project, for render progress and verification."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def timeline_length(project_path: Path | str) -> tuple[int, float] | None:
    """``(frames, fps)`` of the longest playlist (clips and blanks), or ``None``.

    ``None`` when the project cannot be parsed or has no entries: callers then
    skip the checks that need it rather than guess.
    """
    path = Path(project_path)
    if path.suffix.lower() != ".kdenlive":
        return None
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    try:
        project = parse_project(path)
    except Exception as exc:  # noqa: BLE001 -- best-effort: the render itself reports a bad project
        logger.debug("timeline_length: cannot parse %s: %s", path, exc)
        return None
    frames = max(
        (sum(max(0, e.out_point - e.in_point + 1) for e in playlist.entries)
         for playlist in project.playlists),
        default=0,
    )
    fps = float(project.profile.fps or 0)
    if frames <= 0 or fps <= 0:
        return None
    return frames, fps
