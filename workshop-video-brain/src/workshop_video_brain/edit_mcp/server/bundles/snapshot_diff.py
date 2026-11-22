"""``snapshot_diff``: what changed between two versions of the project, in plain sentences.

Read-only (no snapshot, no write). Diff logic in ``pipelines/project_diff``.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    corrupt_project,
    from_exception,
    invalid_input,
    missing_file,
    not_found,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _validate_workspace_path


@mcp.tool()
@tool_guard
def snapshot_diff(workspace_path: str, a: str = "previous", b: str = "latest", max_changes: int = 200) -> dict:
    """Explain what changed from version ``a`` to version ``b`` of the project.

    ``a`` / ``b``: ``latest``, ``previous`` (the working copy before latest), a
    snapshot id from ``snapshot_list``, or a .kdenlive path inside the
    workspace. Reports tracks, clips (added, removed, moved, trimmed,
    replaced), clip effects and track filters, transitions, guides, bin clips
    and duration, as structured ``changes`` plus a ``text`` you can read out.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import ProjectParseError, parse_project
    from workshop_video_brain.edit_mcp.pipelines.project_diff import diff_projects
    from workshop_video_brain.edit_mcp.server.tools_helpers._versions import VersionNotFound, resolve_version

    if isinstance(max_changes, bool) or not isinstance(max_changes, int) or max_changes < 1:
        return invalid_input(f"max_changes must be a whole number >= 1, got {max_changes!r}",
                             "Pass max_changes=200.", param="max_changes")
    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    paths = {}
    for name, ref in (("a", a), ("b", b)):
        try:
            paths[name] = resolve_version(ws_path, ref)
        except VersionNotFound as exc:
            return not_found("Project version", str(ref), hint=f"{exc} Run snapshot_list for snapshot ids.")
        except FileNotFoundError as exc:
            return missing_file(str(exc).split(": ", 1)[-1], "project file")
    projects = {}
    for name, path in paths.items():
        try:
            projects[name] = parse_project(path)
        except ProjectParseError as exc:
            return corrupt_project(str(path), exc)
    diff = diff_projects(projects["a"], projects["b"], max_changes=max_changes)
    return _ok({"a": str(paths["a"]), "b": str(paths["b"]), **diff})
