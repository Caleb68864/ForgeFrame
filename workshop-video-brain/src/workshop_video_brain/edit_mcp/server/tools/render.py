"""Render, render-profile, and QC tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _validate_workspace_path,
    latest_project,
    _load_latest_project,
    _save_patched,
)





# ---------------------------------------------------------------------------
# Render tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def render_preview(workspace_path: str) -> dict:
    """Render the latest working copy project with the preview profile.

    Requires melt (MLT) or ffmpeg to be available.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Render job status and output path.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render

        working_copies = ws_path / "projects" / "working_copies"
        if not working_copies.exists():
            return _err(
                "No projects/working_copies/ directory found. "
                "Run project_create_working_copy first."
            )
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return err("No .kdenlive files found in projects/working_copies/", error_type="missing_file", suggestion="Create a working copy first with project_create_working_copy, or verify this workspace has been initialised.")

        latest = latest_project(kdenlive_files)
        job = run_render(
            workspace_root=ws_path,
            project_path=latest,
            profile_name="preview",
        )
        return _ok({
            "job_id": str(job.id),
            "status": job.status,
            "project_path": job.project_path,
            "output_path": job.output_path,
            "log_path": job.log_path,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def render_status(workspace_path: str) -> dict:
    """List all render jobs for the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of render jobs with status, profile, and output paths.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders

        jobs = list_renders(workspace_path)
        return _ok({
            "jobs": [
                {
                    "id": str(j.id),
                    "status": j.status,
                    "profile": j.profile,
                    "output_path": j.output_path,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in jobs
            ],
            "count": len(jobs),
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Render tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def render_final_tool(
    workspace_path: str,
    profile: str,
    output_name: str = "",
    project_file: str = "",
) -> dict:
    """Render the workspace project using a named render profile.

    Creates a full-quality render of the latest .kdenlive project file
    in the workspace using the specified profile (e.g. "youtube-1080p",
    "master-prores").

    Args:
        workspace_path: Absolute path to the workspace root directory.
        profile: Render profile name (see render_list_profiles for options).
        output_name: Optional base name for the output file. Defaults to
                     the profile name with a timestamp.

    Returns:
        RenderResult with output_path, profile_used, duration_seconds,
        file_size_bytes, and codec_info.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.render_final import (
            render_final as _render_final,
        )
        from dataclasses import asdict

        name = output_name.strip() if output_name else None
        proj = project_file.strip() if project_file else None
        result = _render_final(ws_root, profile, output_name=name, project_file=proj)

        data = asdict(result)
        data["output_path"] = str(data["output_path"])
        return _ok(data)
    except FileNotFoundError as exc:
        return from_exception(exc)
    except RuntimeError as exc:
        return from_exception(exc)
    except Exception as exc:
        return _err(f"Render failed: {exc}")


@mcp.tool()
@tool_guard
def render_list_profiles() -> dict:
    """List all available render profiles with their names.

    Returns a list of profile names that can be passed to render_final.
    Profiles include platform-specific presets (youtube-1080p, youtube-4k,
    vimeo-hq) and master formats (master-prores, master-dnxhr).

    Returns:
        List of profile name strings.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.render.profiles import (
            list_profiles,
            load_profile,
        )
        names = list_profiles()
        profiles = []
        for name in names:
            try:
                p = load_profile(name)
                profiles.append({
                    "name": name,
                    "codec": p.video_codec,
                    "resolution": f"{p.width}x{p.height}",
                    "fps": p.fps,
                })
            except Exception:
                profiles.append({"name": name, "codec": "unknown"})
        return _ok({"profiles": profiles})
    except Exception as exc:
        return _err(f"Failed to list profiles: {exc}")




# ---------------------------------------------------------------------------
# Project profile tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def project_setup_profile(
    workspace_path: str,
    width: int,
    height: int,
    fps_num: int,
    fps_den: int,
    colorspace: int = 709,
) -> dict:
    """Set up project profile (resolution, fps, colorspace).

    Args:
        workspace_path: Path to workspace root.
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps_num: Frame rate numerator (e.g. 30 for 30fps, 30000 for 29.97).
        fps_den: Frame rate denominator (e.g. 1 for 30fps, 1001 for 29.97).
        colorspace: ITU colorspace code: 601, 709 (default), or 240.
    """
    from workshop_video_brain.edit_mcp.pipelines.project_profile import set_project_profile
    try:
        ws_path, project, latest = _load_latest_project(workspace_path)
        updated = set_project_profile(project, width, height, fps_num, fps_den, colorspace)
        out_path = _save_patched(ws_path, updated, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "width": width,
            "height": height,
            "fps_num": fps_num,
            "fps_den": fps_den,
            "colorspace": colorspace,
        })
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def project_match_source(workspace_path: str, source_file: str) -> dict:
    """Probe a source file and return recommended project profile settings.

    Args:
        workspace_path: Path to workspace root.
        source_file: Path to source media file, relative to workspace root.
    """
    from workshop_video_brain.edit_mcp.pipelines.project_profile import match_profile_to_source
    try:
        source_path = Path(workspace_path) / source_file
        result = match_profile_to_source(source_path)
        return _ok(result)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def qc_check(file_path: str, checks: str = "") -> dict:
    """Run automated quality checks on a rendered media file.

    Checks: black_frames, silence, loudness, clipping, file_size.
    Pass a comma-separated subset or leave empty for all checks.
    """
    from workshop_video_brain.edit_mcp.pipelines.qc_check import run_qc

    p = Path(file_path)
    if not p.exists():
        return err(f"File not found: {file_path}", error_type="missing_file", suggestion="Check the file path is correct and the file exists.", path=str(file_path))

    check_list: list[str] | None = None
    if checks.strip():
        check_list = [c.strip() for c in checks.split(",") if c.strip()]

    report = run_qc(p, check_list)
    return _ok(report.model_dump())
