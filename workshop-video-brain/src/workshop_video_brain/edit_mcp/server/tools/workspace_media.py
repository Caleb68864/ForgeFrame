"""Workspace, media ingest, proxy, and VFR/CFR tools.

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
    _require_workspace,
    _validate_workspace_path,
)





# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def workspace_create(title: str, media_root: str, vault_path: str = "") -> dict:
    """Create a new workspace with the given title and media root.

    Args:
        title: Human-readable project title.
        media_root: Absolute path to the folder containing raw media files.
        vault_path: Optional path to an Obsidian vault root.

    Returns:
        Workspace metadata including workspace_root and workspace_id.
    """
    try:
        if not title or not title.strip():
            return err("title must be a non-empty string",
                       suggestion="Pass a title for the workspace, e.g. \"My Bench Build\".")
        if not media_root or not media_root.strip():
            return err("media_root must be a non-empty string",
                       suggestion="Pass the path to the folder holding your source recordings.")
        media_root_path = Path(media_root)
        if not media_root_path.exists():
            return err(f"media_root does not exist: {media_root}",
                       suggestion="Check the path is correct; it must point at an existing folder of source media.")
        if not media_root_path.is_dir():
            return err(f"media_root is not a directory: {media_root}",
                       suggestion="Point media_root at a folder, not a single file.")
        from workshop_video_brain.workspace.manager import WorkspaceManager
        config = {"vault_path": vault_path} if vault_path else {}
        workspace = WorkspaceManager.create(
            title=title,
            media_root=media_root,
            config=config,
        )
        return _ok({
            "workspace_id": str(workspace.id),
            "workspace_root": workspace.workspace_root,
            "media_root": workspace.media_root,
            "title": workspace.project.title,
            "slug": workspace.project.slug,
            "status": workspace.project.status,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def workspace_status(workspace_path: str) -> dict:
    """Return manifest data for an existing workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Manifest fields: workspace_id, title, slug, status, media_root, etc.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        from workshop_video_brain.workspace.manifest import read_manifest
        manifest = read_manifest(workspace_path)
        return _ok({
            "workspace_id": str(manifest.workspace_id),
            "project_title": manifest.project_title,
            "slug": manifest.slug,
            "status": manifest.status,
            "media_root": manifest.media_root,
            "vault_note_path": manifest.vault_note_path,
            "content_type": manifest.content_type,
            "created_at": manifest.created_at.isoformat(),
            "updated_at": manifest.updated_at.isoformat(),
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Media tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def media_ingest(workspace_path: str) -> dict:
    """Run the full ingest pipeline: scan, proxy, transcribe, detect silence.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        IngestReport summary with counts of scanned, proxied, transcribed assets.
    """
    try:
        p, workspace = _require_workspace(workspace_path)
        raw_dir = p / "media" / "raw"
        if not raw_dir.exists():
            return err(
                f"media/raw/ does not exist in this workspace: {raw_dir}",
                suggestion="Create media/raw/ and copy your source recordings into it, then run media_ingest again.",
            )
        import shutil as _shutil
        if not _shutil.which("ffmpeg"):
            return err(
                "ffmpeg is not available on PATH.",
                suggestion="Install FFmpeg and make sure it is on your PATH (e.g. `sudo pacman -S ffmpeg` or from https://ffmpeg.org/download.html), then run media_ingest again.",
            )
        from workshop_video_brain.app.config import load_config
        from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
        config = load_config()
        report = run_ingest(workspace, config)
        return _ok({
            "scanned_count": report.scanned_count,
            "proxied_count": report.proxied_count,
            "transcribed_count": report.transcribed_count,
            "silence_detected_count": report.silence_detected_count,
            "errors": report.errors,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def media_list_assets(workspace_path: str) -> dict:
    """List media assets found in the workspace media/raw directory.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of asset file paths found under media/raw/.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        raw_dir = ws_path / "media" / "raw"
        if not raw_dir.exists():
            return _ok({"assets": [], "count": 0, "message": "media/raw directory not found"})
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        assets = scan_directory(raw_dir)
        return _ok({
            "assets": [
                {
                    "id": str(a.id),
                    "path": a.path,
                    "media_type": a.media_type,
                    "duration_seconds": a.duration_seconds,
                    "file_size_bytes": a.file_size_bytes,
                }
                for a in assets
            ],
            "count": len(assets),
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Proxy tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def proxy_generate(workspace_path: str) -> dict:
    """Generate proxy files for all media assets that need them.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of proxies generated and any errors encountered.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
            ProxyPolicy,
            generate_proxy,
            needs_proxy,
            proxy_path_for,
        )
        raw_dir = ws_path / "media" / "raw"
        proxy_dir = ws_path / "media" / "proxies"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        if not raw_dir.exists():
            return _ok({"proxied": 0, "skipped": 0, "errors": []})
        assets = scan_directory(raw_dir)
        policy = ProxyPolicy()
        proxied, skipped, errors = 0, 0, []
        for asset in assets:
            if needs_proxy(asset, policy):
                existing = proxy_path_for(asset, proxy_dir)
                if existing.exists():
                    skipped += 1
                    continue
                try:
                    generate_proxy(asset, proxy_dir, policy)
                    proxied += 1
                except Exception as exc:
                    errors.append(str(exc))
            else:
                skipped += 1
        return _ok({"proxied": proxied, "skipped": skipped, "errors": errors})
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# VFR Detection tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def media_check_vfr(workspace_path: str) -> dict:
    """Scan workspace for variable frame rate (VFR) video files.

    VFR media causes audio drift and editing artifacts. This tool identifies
    files that need transcode to constant frame rate before editing.

    Args:
        workspace_path: Absolute path to the workspace root directory.

    Returns:
        Report with files_checked count, list of VFR files with divergence
        details, and all_cfr flag.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.vfr_check import check_vfr
        from dataclasses import asdict
        report = check_vfr(ws_root)
        data = asdict(report)
        return _ok(data)
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except Exception as exc:
        return err(f"VFR check failed: {exc}",
                   suggestion="Confirm ffprobe is installed and the workspace media is readable, then retry.")


@mcp.tool()
@tool_guard
def media_transcode_cfr(
    workspace_path: str,
    file_path: str,
    target_fps: int = 0,
) -> dict:
    """Transcode a VFR video file to constant frame rate (CFR).

    Produces a new file alongside the source with a '_cfr' suffix.

    Args:
        workspace_path: Absolute path to the workspace root directory.
        file_path: Path to the VFR file (absolute or relative to workspace).
        target_fps: Target frame rate. Use 0 to auto-detect from source.

    Returns:
        Path to the new CFR file.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        source = Path(file_path)
        if not source.is_absolute():
            source = ws_root / source
        if not source.exists():
            return err(f"Source file not found: {source}",
                       suggestion="Check the file_path; it resolves under the workspace root unless absolute.")

        from workshop_video_brain.edit_mcp.pipelines.vfr_check import transcode_to_cfr
        fps = target_fps if target_fps > 0 else None
        output = transcode_to_cfr(source, target_fps=fps)
        return _ok({"output_path": str(output), "target_fps": target_fps or "auto"})
    except (ValueError, FileNotFoundError) as exc:
        return from_exception(exc)
    except RuntimeError as exc:
        return from_exception(exc)
    except Exception as exc:
        return err(f"Transcode failed: {exc}",
                   suggestion="Confirm ffmpeg is installed and the source is a valid video file, then retry.")
