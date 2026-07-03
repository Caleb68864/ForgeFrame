"""Shared helpers for MCP tool registrations.

Extracted from `server/tools.py` so that generated per-effect wrapper modules
(`pipelines/effect_wrappers/*.py`) can import them without importing the
giant `server.tools` module (avoiding circular imports + slow startup).

Also exposes `register_effect_wrapper` -- a decorator that applies
`@mcp.tool()` and tracks the wrapped function name in a module-level list
for traceability.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


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


# ---------------------------------------------------------------------------
# Response shape helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    return {"status": "success", "data": data}


def _err(message: str) -> dict:
    return {"status": "error", "message": message}


# ---------------------------------------------------------------------------
# Workspace validation
# ---------------------------------------------------------------------------

def _validate_workspace_path(workspace_path: str) -> Path:
    """Validate workspace_path: must be non-empty, exist, and be a directory.

    Raises ValueError with a clear message if any check fails.
    """
    if not workspace_path or not workspace_path.strip():
        raise ValueError("workspace_path must be a non-empty string")
    p = Path(workspace_path)
    if not p.exists():
        raise FileNotFoundError(f"Workspace path does not exist: {workspace_path}")
    if not p.is_dir():
        raise ValueError(f"Workspace path is not a directory: {workspace_path}")
    return p


def _require_workspace(workspace_path: str):
    """Return (Path, Workspace) or raise ValueError."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    p = _validate_workspace_path(workspace_path)
    return p, WorkspaceManager.open(p)


# ---------------------------------------------------------------------------
# Effect wrapper registration
# ---------------------------------------------------------------------------

__wrapped_effects__: list[str] = []


def register_effect_wrapper(fn):
    """Decorator combining `@mcp.tool()` + module-level export tracking.

    Generated effect wrapper modules apply this decorator so each wrapper
    function both registers with the FastMCP singleton and appears in the
    `__wrapped_effects__` list for traceability/testing.
    """
    from workshop_video_brain.server import mcp
    __wrapped_effects__.append(fn.__name__)
    return mcp.tool()(fn)


# ---------------------------------------------------------------------------
# Cross-cutting project/playlist/filter helpers (relocated from server/tools.py)
# ---------------------------------------------------------------------------


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


_VALID_COLOR_FORMATS_MSG = (
    "Invalid color. Expected '#RRGGBB' or '#RRGGBBAA' hex format."
)


def _build_filter_xml(mlt_service: str, kdenlive_id: str, track: int, clip: int,
                      props: list[tuple[str, str]]) -> str:
    """Build a Kdenlive/MLT ``<filter>`` XML string with the usual attrs.

    ``mlt_service`` / ``kdenlive_id`` are normalised to the installed-repository
    (dot-form) asset ids via :func:`normalize_effect_id` so Kdenlive resolves
    them without a "Fixed" pass.
    """
    import xml.etree.ElementTree as _ET
    # Normalise to installed-repository (dot-form) asset ids so Kdenlive resolves
    # the effect without a "Fixed" pass:
    #   * avfilter.*/frei0r.*  -> kdenlive_id = mlt_service (dot form)
    #   * the Transform effect (affine + kdenlive_id="transform" + 5-value rect)
    #     is qtblend in modern Kdenlive (FIX-2b).  pan_zoom / motion tracking use
    #     ``transition.rect`` (kdenlive_id != "transform") and are untouched.
    _prop_names = tuple(name for name, _ in props)
    if mlt_service.startswith(("avfilter.", "frei0r.")):
        kdenlive_id = mlt_service
    elif (
        mlt_service == "affine"
        and kdenlive_id == "transform"
        and "transition.rect" not in _prop_names
    ):
        mlt_service, kdenlive_id = "qtblend", "qtblend"
    root = _ET.Element(
        "filter",
        {
            "mlt_service": mlt_service,
            "track": str(track),
            "clip_index": str(clip),
        },
    )
    svc = _ET.SubElement(root, "property", {"name": "mlt_service"})
    svc.text = mlt_service
    kid = _ET.SubElement(root, "property", {"name": "kdenlive_id"})
    kid.text = kdenlive_id
    for name, value in props:
        prop = _ET.SubElement(root, "property", {"name": name})
        prop.text = value
    return _ET.tostring(root, encoding="unicode")


def _lookup_catalog_by_service(mlt_service: str):
    """Return (kdenlive_id, EffectDef) for a given mlt_service, else (None, None)."""
    try:
        from workshop_video_brain.edit_mcp.pipelines import effect_catalog as _catalog
    except ModuleNotFoundError:
        return None, None
    for kid, eff in _catalog.CATALOG.items():
        if eff.mlt_service == mlt_service:
            return kid, eff
    return None, None
