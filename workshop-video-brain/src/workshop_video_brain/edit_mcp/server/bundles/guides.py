"""Project guide + YouTube chapter MCP tools.

First-class guide tools (``guide_add`` / ``guide_list`` / ``guide_remove``) and
``publish_chapters`` -- tutorial #22 ("Using Guides to add YouTube Chapters").

The Guide model + AddGuide intent already exist; this bundle is the first MCP
surface that exposes them.  All project-writing tools snapshot before and after
writing and return the ``{"status": ...}`` dict shape used across the server.

Auto-imported by ``server/bundles/__init__``; registers via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _err
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.pipelines import guides as guides_pipeline
# Reuse the publishing pipeline's marker reader for chapter_candidate markers
# (wiring publish_chapters to the existing publish_* style without editing it).
from workshop_video_brain.edit_mcp.pipelines.publishing import (
    _read_chapters_from_workspace,
)
from workshop_video_brain.workspace import create_snapshot


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _find_workspace_root(start: Path) -> Path | None:
    """Walk up from *start* looking for a ``workspace.yaml`` marker."""
    candidates = [start] if start.is_dir() else []
    candidates.extend(start.parents)
    for parent in candidates:
        if (parent / "workspace.yaml").exists():
            return parent
    return None


# ---------------------------------------------------------------------------
# guide_add / guide_list / guide_remove
# ---------------------------------------------------------------------------

@mcp.tool()
def guide_add(
    project_file: str,
    at_seconds: float,
    label: str,
    category: str | None = None,
) -> dict:
    """Add a timeline guide to a Kdenlive project at *at_seconds*.

    Args:
        project_file: Path to the .kdenlive project (absolute or cwd-relative).
        at_seconds: Guide position in seconds (converted to frames at project fps).
        label: Guide label / chapter name.
        category: Optional guide category (Kdenlive category index as a string).

    Returns a success dict with the updated guide list and the Kdenlive
    ``docproperties.guides`` JSON.  NOTE: our serializer writes legacy
    ``<guide>`` elements, so guides added here round-trip through our own
    parser but may not display in a Kdenlive 24.x/25.x GUI until the serializer
    emits the JSON property (see guides-chapters.md).
    """
    try:
        project_path = _resolve(project_file)
        if not project_path.exists():
            return _err(f"Project file not found: {project_file}")
        if at_seconds < 0:
            return _err("at_seconds must be >= 0")

        project = parse_project(project_path)
        ws_root = _find_workspace_root(project_path)
        if ws_root:
            create_snapshot(ws_root, project_path, description="before_guide_add")

        new_project = guides_pipeline.add_guide(
            project, at_seconds, label, category
        )
        serialize_project(new_project, project_path)

        snapshot_id = None
        if ws_root:
            snap = create_snapshot(
                ws_root, project_path, description="after_guide_add"
            )
            snapshot_id = snap.snapshot_id

        return _ok(
            {
                "guides": guides_pipeline.list_guides(new_project),
                "guide_count": len(new_project.guides),
                "docproperties_guides_json": (
                    guides_pipeline.guides_docproperties_json(new_project)
                ),
                "snapshot_id": snapshot_id,
            }
        )
    except (ValueError, FileNotFoundError, IndexError) as exc:
        return _err(str(exc))


@mcp.tool()
def guide_list(project_file: str) -> dict:
    """List all guides in a Kdenlive project (read-only)."""
    try:
        project_path = _resolve(project_file)
        if not project_path.exists():
            return _err(f"Project file not found: {project_file}")
        project = parse_project(project_path)
        return _ok(
            {
                "guides": guides_pipeline.list_guides(project),
                "guide_count": len(project.guides),
                "docproperties_guides_json": (
                    guides_pipeline.guides_docproperties_json(project)
                ),
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))


@mcp.tool()
def guide_remove(project_file: str, at_seconds_or_label: str) -> dict:
    """Remove guides by time (numeric seconds) or by label (string).

    Args:
        project_file: Path to the .kdenlive project.
        at_seconds_or_label: A number/numeric string matches by position;
            any other string matches by label (case-insensitive).
    """
    try:
        project_path = _resolve(project_file)
        if not project_path.exists():
            return _err(f"Project file not found: {project_file}")

        project = parse_project(project_path)
        new_project, removed = guides_pipeline.remove_guide(
            project, at_seconds_or_label
        )
        if not removed:
            return _err(f"No guide matched: {at_seconds_or_label}")

        ws_root = _find_workspace_root(project_path)
        if ws_root:
            create_snapshot(
                ws_root, project_path, description="before_guide_remove"
            )
        serialize_project(new_project, project_path)
        snapshot_id = None
        if ws_root:
            snap = create_snapshot(
                ws_root, project_path, description="after_guide_remove"
            )
            snapshot_id = snap.snapshot_id

        return _ok(
            {
                "removed": removed,
                "removed_count": len(removed),
                "guides": guides_pipeline.list_guides(new_project),
                "guide_count": len(new_project.guides),
                "snapshot_id": snapshot_id,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# publish_chapters
# ---------------------------------------------------------------------------

@mcp.tool()
def publish_chapters(
    project_file_or_workspace: str,
    min_gap_seconds: float = 10.0,
) -> dict:
    """Export guides + chapter markers as YouTube chapter text.

    Accepts either a .kdenlive project file (guides + workspace markers are
    collected) or a workspace directory (chapter_candidate markers only).
    Enforces YouTube's first-chapter-at-0:00 rule and the *min_gap_seconds*
    minimum chapter length, then writes ``reports/chapters.txt`` and returns
    the text.  Style mirrors the existing ``publish_*`` pipelines.

    Returns a success dict with ``chapters_text``, the output ``path``, chapter
    ``count`` and any YouTube-rule ``warnings``.
    """
    try:
        target = _resolve(project_file_or_workspace)
        if not target.exists():
            return _err(f"Path not found: {project_file_or_workspace}")

        chapters: list[dict] = []
        if target.is_dir():
            ws_root = target if (target / "workspace.yaml").exists() else None
            if ws_root is None:
                ws_root = _find_workspace_root(target)
        else:
            project = parse_project(target)
            chapters.extend(
                guides_pipeline.collect_project_guide_chapters(project)
            )
            ws_root = _find_workspace_root(target)

        if ws_root is not None:
            chapters.extend(_read_chapters_from_workspace(ws_root))

        prepared = guides_pipeline.prepare_chapters(chapters, min_gap_seconds)
        text = guides_pipeline.format_chapter_lines(prepared)
        warnings = guides_pipeline.youtube_chapter_warnings(
            prepared, min_gap_seconds
        )

        out_root = ws_root if ws_root is not None else (
            target if target.is_dir() else target.parent
        )
        reports_dir = out_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_path = reports_dir / "chapters.txt"
        out_path.write_text(text, encoding="utf-8")

        return _ok(
            {
                "chapters_text": text,
                "path": str(out_path),
                "count": len(prepared),
                "warnings": warnings,
            }
        )
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
