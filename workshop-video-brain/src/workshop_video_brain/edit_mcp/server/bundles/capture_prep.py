"""``capture_prep_checklist`` MCP tool -- pre-shoot capture checklist.

Auto-imported by ``server/bundles/__init__.py``. Read-only shell over
``production_brain.skills.capture_prep``: loads ``reports/shot_plan.json``
(or a generic plan), and returns the checklist markdown. Writes nothing.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    missing_file,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp


@mcp.tool()
@tool_guard
def capture_prep_checklist(
    workspace_path: str,
    target_resolution: str = "1920x1080",
    target_fps: int = 30,
) -> dict:
    """Generate a pre-shoot capture checklist from the workspace's shot plan.

    Reads ``reports/shot_plan.json`` (written by ``ff-new-project`` / the shot
    plan step); without one, returns a generic checklist and a ``note``.
    Covers camera settings, audio, lighting, sync, and a shot order grouped to
    minimise setup changes. Read-only.

    Args:
        workspace_path: Path to the workspace root.
        target_resolution: Camera resolution as ``WxH``, e.g. ``"3840x2160"``.
        target_fps: Whole-number frame rate, e.g. 24, 30 or 60.

    Returns:
        ``title``, ``shot_plan_path`` (or null), ``shot_count``,
        ``target_resolution``, ``target_fps``, ``markdown`` and, when no shot
        plan exists, ``note``.
    """
    from workshop_video_brain.production_brain.skills.capture_prep import (
        capture_prep_payload,
        load_shot_plan,
    )

    try:
        ws_path = _validate_workspace_path(workspace_path)
    except FileNotFoundError:
        return missing_file(workspace_path, "Workspace path")
    except ValueError as exc:
        return invalid_input(
            str(exc),
            "Pass the absolute path to your workspace directory (the folder "
            "containing projects/, media/, reports/).",
            param="workspace_path",
        )

    try:
        plan, plan_path = load_shot_plan(ws_path)
    except ValueError as exc:
        return invalid_input(
            str(exc),
            "Fix or delete reports/shot_plan.json (delete it to get a generic "
            "checklist), or regenerate the shot plan.",
        )

    try:
        payload = capture_prep_payload(plan, plan_path, target_resolution, target_fps)
    except ValueError as exc:
        return invalid_input(
            str(exc),
            "Use a whole-number target_fps such as 24, 30 or 60 and a "
            "target_resolution like '1920x1080' or '3840x2160'.",
            target_resolution=target_resolution,
            target_fps=target_fps,
        )
    return _ok(payload)
