"""Bundle tools: generate a matte video locally with a segmentation engine.

Registers ``mask_generate`` (source → black/white matte video) and
``mask_generate_and_apply`` (generate + wire the matte onto a clip as alpha via
the existing Shape Alpha pipeline). This is the *producing* half of the SAM2
story; the *consuming* half is ``mask_set_from_file`` (``shape_alpha_mask.py``).

Additive, self-contained: auto-discovered by ``server/bundles/__init__.py`` and
registers via ``from workshop_video_brain.server import mcp``. ``mask_generate``
only writes into ``media/derived_masks/`` (never ``media/raw``) and takes no
snapshot; ``mask_generate_and_apply`` snapshots the project before editing it.

If the requested engine is not installed, both tools return a clear ``_err``
with the exact ``pip install`` command — they never crash.
"""
from __future__ import annotations

from pathlib import Path

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
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    cleanup_partial_output as _cleanup_partial,
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}


def _find_video_file(workspace_path: Path, source: str) -> Path | None:
    """Locate a video: explicit path (abs or ws-relative) or latest in raw.

    Mirrors ``bundles/stabilize.py::_find_video_file``.
    """
    if source and source.strip():
        p = Path(source)
        if not p.is_absolute():
            p = workspace_path / source
        return p
    raw_dir = workspace_path / "media" / "raw"
    if not raw_dir.exists():
        return None
    candidates = sorted(
        (f for f in raw_dir.iterdir()
         if f.is_file() and f.suffix.lower() in _VIDEO_EXTS),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _generate(
    ws_path: Path,
    source: str,
    subject: str,
    engine: str,
    box: str,
    invert: bool,
    feather_px: int,
    model: str,
    output_name: str,
    max_frames: int,
) -> dict:
    """Shared matte-generation core → result dict from the pipeline (or _err)."""
    from workshop_video_brain.edit_mcp.pipelines import ai_mask

    src = _find_video_file(ws_path, source)
    if src is None:
        return err("No video file found. Provide source or add files to media/raw/.",
                   suggestion="Pass source pointing at a video file, or drop a clip into media/raw/ so the tool can pick it up automatically.")
    if not src.exists():
        return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

    out_dir = ws_path.joinpath(*ai_mask.DERIVED_MASKS_DIR)
    try:
        result = ai_mask.generate_matte(
            src, out_dir,
            subject=subject, engine=engine, box=box, invert=invert,
            feather_px=feather_px, model=model, output_name=output_name,
            max_frames=max_frames,
        )
    except ai_mask.EngineUnavailable as exc:
        return err(str(exc), error_type=MISSING_DEPENDENCY, suggestion="Install the requested segmentation engine as shown above, or pass engine='rembg' (the lightest CPU/no-torch engine).")
    except (ValueError, TypeError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if not result.get("success"):
        # generate_matte writes into a TemporaryDirectory and only moves the
        # final matte out on success, but if encode half-wrote the destination,
        # clear it so no partial matte is left behind.
        _cleanup_partial(ai_mask.derived_mask_path(src, out_dir, output_name or None))
        return error_from_pipeline_result(
            result, "matte generation failed", path=str(src),
        )
    return _ok({"input": str(src), **{k: v for k, v in result.items() if k != "success"}})


@mcp.tool()
@tool_guard
def mask_generate(
    workspace_path: str,
    source: str = "",
    subject: str = "person",
    engine: str = "auto",
    box: str = "",
    invert: bool = False,
    feather_px: int = 0,
    model: str = "",
    output_name: str = "",
    max_frames: int = 0,
) -> dict:
    """Generate a black/white **matte video** for a clip using a local segmenter.

    Produces a matte (white = keep) matching the source's resolution/fps/
    duration, written to ``media/derived_masks/``. The source in ``media/raw`` is
    never modified. Feed the result into ``mask_set_from_file`` (or use
    ``mask_generate_and_apply``) to cut out the subject.

    Args:
        workspace_path: Workspace root.
        source: Video path (abs or workspace-relative). Empty → latest in
            ``media/raw/``.
        subject: What to keep. ``"person"`` (and synonyms) biases the rembg
            engine to its human-segmentation model; other values use the light
            default model. For class-prompted / click engines see ``engine``.
        engine: ``"auto"`` (default → rembg, the lightest CPU/no-torch engine),
            or explicit ``"rembg"``/``"sam2"``/``"yolo"``. Missing/second-tier
            engines return an error with the ``pip install`` command.
        box: Optional ``"x,y,w,h"`` region; the matte is restricted to it
            (outside → black).
        invert: Invert the matte (keep the background instead of the subject).
        feather_px: Gaussian edge feather in pixels (0 = hard edge).
        model: Override the segmentation model (rembg model name, e.g.
            ``u2net``, ``isnet-general-use``, ``birefnet-general``).
        output_name: Matte filename. Default ``{stem}_matte.mp4``.
        max_frames: Cap frames processed (0 = whole clip); handy for previews.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    return _generate(
        ws_path, source, subject, engine, box, invert, feather_px,
        model, output_name, max_frames,
    )


@mcp.tool()
@tool_guard
def mask_generate_and_apply(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    source: str = "",
    subject: str = "person",
    engine: str = "auto",
    box: str = "",
    invert: bool = False,
    feather_px: int = 0,
    model: str = "",
    output_name: str = "",
    max_frames: int = 0,
    mix: int = 100,
    softness: float = 0.1,
    use_threshold: bool = True,
) -> dict:
    """Generate a matte video, then wire it onto a clip's alpha (one call).

    Runs :func:`mask_generate`, then inserts a Shape Alpha (MLT ``shape``)
    effect at the TOP of the clip's stack referencing the generated matte —
    reusing the existing ``pipelines/shape_alpha`` builder and the same
    parse/patch/serialize path as ``mask_set_from_file``. The matte carries the
    mask in its **luma**, so it is consumed with ``use_luminance=True``. A
    snapshot is taken before the project is written.

    Extra args beyond :func:`mask_generate`: ``mix`` (luma threshold %),
    ``softness`` (edge 0..1), ``use_threshold`` (apply the ``mix`` threshold).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.pipelines import shape_alpha
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    # 1. Generate the matte (never touches the project).
    gen = _generate(
        ws_path, source, subject, engine, box, invert, feather_px,
        model, output_name, max_frames,
    )
    if gen["status"] != "success":
        return gen
    matte_path = gen["data"]["output"]

    # 2. Build the Shape Alpha effect from the generated matte.
    try:
        xml = shape_alpha.build_shape_alpha_xml(
            (track, clip),
            matte_path,
            mix=mix,
            softness=softness,
            invert=False,  # invert already baked into the matte if requested.
            use_luminance=True,  # matte carries the mask in luma.
            use_mix=use_threshold,
        )
    except (ValueError, TypeError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    # 3. Snapshot + patch + serialize (mirrors mask_set_from_file).
    try:
        record = create_snapshot(
            ws_path, project_path, description="before_mask_generate_and_apply"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    project = parse_project(project_path)
    try:
        patcher.insert_effect_xml(project, (track, clip), xml, position=0)
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    serialize_project(project, project_path)

    return _ok({
        "matte": gen["data"],
        "effect_index": 0,
        "type": "image_alpha",
        "mlt_service": "shape",
        "mask_file": matte_path,
        "snapshot_id": snapshot_id,
    })
