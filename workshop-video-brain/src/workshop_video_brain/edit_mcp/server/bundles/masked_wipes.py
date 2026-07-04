"""Masked / custom-luma wipe transition MCP tools.

Auto-imported by ``bundles/__init__`` (which walks this package on import), so
this file just registers its tools via ``@mcp.tool()`` on the shared FastMCP
singleton -- no edits to ``server.py`` or ``server/tools.py`` required.

Two tools, derived from tutorials #10 (``tHzP9kJQJeg``, masked shape-reveal
transitions) and #11 (``Ih7c65LsLZc``, custom ``.pgm`` luma-file wipes); analysis
in ``docs/research/2026-07-03-tutorial-effect-analysis/masked-wipe-transitions.md``:

* ``transition_masked_wipe`` -- a luma/wipe transition accepting BOTH built-in
  MLT luma names and user ``.pgm``/``.png`` matte paths, plus ``invert`` and
  ``softness``. Closes SYNTHESIS.md #7's "composite_wipe extension" (the existing
  ``composite_wipe`` tool hardcodes ``luma01.pgm`` with no invert/softness).
* ``effect_luma_key`` -- the ``avfilter.lumakey`` primitive (luminance -> alpha);
  SYNTHESIS.md #7 flags it as non-existent.

Conventions follow ``server/tools.py`` bundle tools: snapshot-before-write,
``_ok``/``_err`` result dicts, deferred imports inside the function body.

Known limitation (plan §1.1/§1.2,
``docs/plans/2026-07-03-kdenlive-mcp-improvements.md``): the transition is placed
outside the ``<tractor>`` and the filter attaches at the MLT root because the
serializer does not read ``position_hint``. Noted, not fixed here.
"""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
)


@mcp.tool()
@tool_guard
def transition_masked_wipe(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    duration_frames: int,
    luma_file: str,
    invert: bool = False,
    softness: float = 0.0,
) -> dict:
    """Add a masked / custom-luma wipe transition between two tracks.

    Writes a ``<transition mlt_service="luma">`` whose ``resource`` is a luma
    matte, feathered by ``softness`` and optionally reversed by ``invert``.

    ``luma_file`` accepts BOTH forms shown in the tutorials:

    * a **built-in luma name** (e.g. ``"luma03"`` / ``"luma03.pgm"``), resolved
      under ``/usr/share/kdenlive/lumas/HD/``; or
    * a **user matte path** to a ``.pgm``/``.png`` grayscale image (absolute,
      relative, or ``~``-prefixed), used verbatim.

    The transition spans ``[start_frame, start_frame + duration_frames]``.
    ``softness`` is the 0..1 edge gradient; ``invert`` reverses the black->white
    ordering of the matte.

    Omissions: built-in names are not existence-checked (install paths vary);
    animated mattes are out of scope; and the transition is subject to the known
    §1.1/§1.2 placement issue (lands outside the ``<tractor>``). A snapshot is
    created before the project is modified.
    """
    from workshop_video_brain.edit_mcp.pipelines.masked_wipes import apply_masked_wipe
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    if duration_frames <= 0:
        return err(f"duration_frames must be positive (got {duration_frames})", suggestion="Pass a positive duration_frames for how long the wipe takes.")
    if not luma_file or not luma_file.strip():
        return invalid_input("luma_file must be a non-empty string", suggestion="Pass a non-empty value for this argument.")

    end_frame = start_frame + duration_frames

    record = create_snapshot(
        ws_path, proj_path, description="before_masked_wipe"
    )

    project = parse_project(proj_path)
    try:
        updated = apply_masked_wipe(
            project,
            track_a=track_a,
            track_b=track_b,
            start_frame=start_frame,
            end_frame=end_frame,
            luma_file=luma_file,
            invert=invert,
            softness=softness,
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(updated, proj_path)

    from workshop_video_brain.edit_mcp.pipelines.masked_wipes import resolve_luma

    return _ok({
        "composition_added": True,
        "luma_file": luma_file,
        "resource": resolve_luma(luma_file),
        "invert": invert,
        "softness": softness,
        "track_a": track_a,
        "track_b": track_b,
        "frames": [start_frame, end_frame],
        "snapshot_id": record.snapshot_id,
    })


@mcp.tool()
@tool_guard
def effect_luma_key(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    threshold: float = 0.0,
    tolerance: float = 0.01,
    softness: float = 0.0,
) -> dict:
    """Add a luminance key (``avfilter.lumakey``) to a clip: luma -> alpha.

    The luma analogue of ``effect_chroma_key``: pixels whose luminance is at/below
    ``threshold`` become transparent, with ``tolerance`` and ``softness``
    feathering the alpha edge. All three are 0..1.

    Omissions: params are emitted under MLT's ``av.`` avfilter convention and the
    service string is passed through unvalidated (like ``effect_add``), so exact
    option availability depends on the local MLT/FFmpeg build; the filter is
    subject to the known §1.1 root-placement issue. A snapshot is created before
    the project is modified.
    """
    from workshop_video_brain.edit_mcp.pipelines.masked_wipes import apply_luma_key
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    proj_path = ws_path / project_file
    if not proj_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    record = create_snapshot(ws_path, proj_path, description="before_luma_key")

    project = parse_project(proj_path)
    try:
        updated = apply_luma_key(
            project,
            track_index=track,
            clip_index=clip,
            threshold=threshold,
            tolerance=tolerance,
            softness=softness,
        )
    except (ValueError, IndexError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(updated, proj_path)
    return _ok({
        "effect_added": True,
        "effect_name": "avfilter.lumakey",
        "track": track,
        "clip": clip,
        "threshold": threshold,
        "tolerance": tolerance,
        "softness": softness,
        "snapshot_id": record.snapshot_id,
    })
