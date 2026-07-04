"""Bundle tool: consume an external matte/mask *file* as a clip's alpha.

Registers ``mask_set_from_file`` -- the file-based counterpart to the
application-side Kdenlive 25.04 Object Mask (SAM2) workflow. SAM2's "Apply
Mask" inserts a Shape Alpha (MLT ``shape``) effect that points at a generated
mask video file; this tool builds that same effect from any matte file so an
agent can wire a SAM2-exported (or otherwise rendered) mask onto a clip
without the GUI.

Additive, self-contained module: it does not edit any shared file. It is
auto-discovered by ``server/bundles/__init__.py`` and registers via
``from workshop_video_brain.server import mcp``.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    invalid_input,
    operation_failed,
    from_exception,
    MISSING_FILE,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _require_workspace,
)


@mcp.tool()
@tool_guard
def mask_set_from_file(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    mask_file: str,
    mix: int = 100,
    softness: float = 0.1,
    invert: bool = False,
    use_luminance: bool = False,
    use_threshold: bool = True,
    mask_in: int = 0,
    mask_out: int = -1,
) -> dict:
    """Insert a Shape Alpha (``shape``) filter consuming an external matte file.

    This is the file-based ``image_alpha`` mask type: it points a clip's alpha
    channel at ``mask_file`` -- e.g. a mask video exported by Kdenlive 25.04's
    Object Mask (SAM2) plugin, a rendered luma wipe, or a hand-painted alpha
    clip. The filter is inserted at the TOP of the clip's effect stack (index
    0), matching ``mask_set``. A snapshot is created before writing.

    Parameters
    ----------
    mask_file:
        Path to the matte (video or image). Stored verbatim in the project;
        not required to exist at call time (SAM2 mattes live in Kdenlive's
        own folder).
    mix:
        Threshold percentage (0-100). Values below are opaque, above are
        transparent -- most useful for luma wipe / luma mattes.
    softness:
        Edge softness around the threshold (0.0-1.0).
    invert:
        Use the inverse of the alpha channel.
    use_luminance:
        Read the matte from image luma instead of its alpha channel (set True
        for luma mattes with no alpha).
    use_threshold:
        Whether to apply the ``mix`` threshold at all. When False, the matte's
        raw luma/alpha is copied straight to the clip alpha.
    mask_in / mask_out:
        Matte start offset / end (``-1`` = run to clip end).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.workspace import create_snapshot
    from workshop_video_brain.edit_mcp.pipelines import shape_alpha

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    try:
        xml = shape_alpha.build_shape_alpha_xml(
            (track, clip),
            mask_file,
            mix=mix,
            softness=softness,
            invert=invert,
            use_luminance=use_luminance,
            use_mix=use_threshold,
            mask_in=mask_in,
            mask_out=mask_out,
        )
    except (ValueError, TypeError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # Parse BEFORE snapshotting so a corrupt project fails cleanly.
    try:
        project = parse_project(project_path)
    except Exception as exc:  # noqa: BLE001 -- corrupt/unparseable project
        return from_exception(exc)

    try:
        patcher.insert_effect_xml(project, (track, clip), xml, position=0)
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_mask_set_from_file"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    serialize_project(project, project_path)
    return _ok({
        "effect_index": 0,
        "type": "image_alpha",
        "mlt_service": "shape",
        "mask_file": mask_file,
        "snapshot_id": snapshot_id,
    })
