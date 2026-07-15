"""Project I/O: latest-project selection + load/save/playlist resolution.

Owns the single source of truth for "which .kdenlive is the latest"
(version-aware, numeric ``_v<N>`` selection) plus the load-latest / serialize /
resolve-playlist helpers shared across the timeline tools.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from workshop_video_brain.edit_mcp.server.tools_helpers._workspace import (
    _validate_workspace_path,
)


# ---------------------------------------------------------------------------
# Latest-project selection (shared, version-aware)
# ---------------------------------------------------------------------------

# Matches a trailing ``_v<N>`` version suffix on a project *stem*, e.g.
# ``my-clip_v12`` -> 12.  Kdenlive working copies are written as
# ``<slug>_v<N>.kdenlive`` by the serializer.
_VERSION_SUFFIX_RE = re.compile(r"_v(\d+)$")


def _project_version_key(path: Path) -> tuple[int, int, float]:
    """Sort key used to pick the *latest* project file.

    Ordering rules (highest wins):

    - Files whose stem ends in ``_v<N>`` rank by the numeric ``N`` so that
      ``slug_v10`` beats ``slug_v2`` (the lexicographic bug this replaces).
    - Files without a numeric ``_v`` suffix fall back to modification time and
      always rank *below* any versioned file (a versioned working copy is the
      canonical edit target).
    """
    m = _VERSION_SUFFIX_RE.search(path.stem)
    if m:
        return (1, int(m.group(1)), 0.0)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (0, 0, mtime)


def latest_project(files: Iterable[Path]) -> Path | None:
    """Return the newest project path from *files*, or ``None`` if empty.

    Selection prefers the highest numeric ``_v<N>`` suffix, falling back to
    modification time for names without one.  This is the single source of
    truth for "which .kdenlive is the latest" across the whole codebase.
    """
    paths = [Path(f) for f in files]
    if not paths:
        return None
    return max(paths, key=_project_version_key)


def _get_video_playlists(project):
    """Return list of video playlist objects (non-audio tracks)."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [p for p in project.playlists if p.id not in audio_ids]


def _load_latest_project(workspace_path: str):
    """Load the latest .kdenlive file from working_copies.  Returns (ws_path, project, latest_path)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    ws_path = _validate_workspace_path(workspace_path)
    working_copies = ws_path / "projects" / "working_copies"
    kdenlive_files = list(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
    if not kdenlive_files:
        raise FileNotFoundError("No .kdenlive files found in projects/working_copies/")
    latest = latest_project(kdenlive_files)
    project = parse_project(latest)
    return ws_path, project, latest


def _save_patched(ws_path, project, workspace_path: str) -> Path:
    """Serialize patched project and return output path."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
    from workshop_video_brain.workspace.manifest import read_manifest
    manifest = read_manifest(workspace_path)
    slug = manifest.slug or "project"
    return serialize_versioned(project, ws_path, slug)


def _resolve_playlist(project, track: int):
    """Resolve track index to a video playlist.  Returns playlist or raises ValueError."""
    video_playlists = _get_video_playlists(project)
    if not video_playlists:
        raise ValueError("No video playlists found in project")
    if track < 0 or track >= len(video_playlists):
        raise ValueError(
            f"track index {track} out of range (project has {len(video_playlists)} video track(s))"
        )
    return video_playlists[track]
