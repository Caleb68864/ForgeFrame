"""Timeline build, project lifecycle, and snapshot tools.

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
    latest_project,
)





# ---------------------------------------------------------------------------
# Timeline tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def timeline_build_review(workspace_path: str, mode: str = "ranked") -> dict:
    """Build a Kdenlive review timeline from workspace markers.

    Args:
        workspace_path: Path to the workspace root directory.
        mode: Ordering mode -- "ranked" (by confidence) or "chronological".

    Returns:
        Path to the generated .kdenlive file and marker count.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.core.models.media import MediaAsset
        from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline

        markers_dir = ws_path / "markers"
        if not markers_dir.exists():
            return _err("No markers/ directory found. Run markers_auto_generate first.")

        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            try:
                raw = _json.loads(mf.read_text(encoding="utf-8"))
                for item in raw:
                    markers.append(Marker(**item))
            except Exception:
                pass

        if not markers:
            return _err("No markers found. Run markers_auto_generate first.")

        kdenlive_path = build_review_timeline(
            markers=markers,
            assets=[],
            workspace_root=ws_path,
            mode=mode,
        )
        return _ok({
            "kdenlive_path": str(kdenlive_path),
            "marker_count": len(markers),
            "mode": mode,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def timeline_build_selects(workspace_path: str, min_confidence: float = 0.5) -> dict:
    """Build a Kdenlive selects timeline from high-confidence markers.

    Args:
        workspace_path: Path to the workspace root directory.
        min_confidence: Minimum confidence score for a marker to be included.

    Returns:
        Path to the generated .kdenlive file and selects count.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        # Coerce min_confidence from string if needed
        try:
            min_confidence = float(min_confidence)
        except (TypeError, ValueError):
            return _err(f"min_confidence must be a number, got: {min_confidence!r}")
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
            build_selects,
            build_selects_timeline,
        )

        markers_dir = ws_path / "markers"
        if not markers_dir.exists():
            return _err("No markers/ directory found. Run markers_auto_generate first.")

        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            try:
                raw = _json.loads(mf.read_text(encoding="utf-8"))
                for item in raw:
                    markers.append(Marker(**item))
            except Exception:
                pass

        if not markers:
            return _err("No markers found. Run markers_auto_generate first.")

        config = MarkerConfig()
        selects = build_selects(markers, config, min_confidence=min_confidence)
        kdenlive_path = build_selects_timeline(
            selects=selects,
            assets=[],
            workspace_root=ws_path,
        )
        return _ok({
            "kdenlive_path": str(kdenlive_path),
            "selects_count": len(selects),
            "min_confidence": min_confidence,
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Project tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def project_create_working_copy(workspace_path: str) -> dict:
    """Create an initial .kdenlive working copy for the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Path to the created .kdenlive file.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.workspace.manifest import read_manifest
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject,
            ProjectProfile,
            Track,
            Playlist,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.utils.naming import slugify

        manifest = read_manifest(workspace_path)
        project = KdenliveProject(
            version="7",
            title=manifest.project_title,
            profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        )
        project.tracks = [
            Track(id="playlist_video", track_type="video", name="Video"),
            Track(id="playlist_audio", track_type="audio", name="Audio"),
        ]
        project.playlists = [
            Playlist(id="playlist_video"),
            Playlist(id="playlist_audio"),
        ]
        project.tractor = {"id": "tractor0", "in": "0", "out": "99999"}

        slug = manifest.slug or slugify(manifest.project_title) or "project"
        out_path = serialize_versioned(project, ws_path, slug)
        return _ok({"kdenlive_path": str(out_path), "title": manifest.project_title})
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def project_validate(workspace_path: str) -> dict:
    """Validate the latest .kdenlive working copy project file.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Validation report with summary and list of issues.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

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
        project = parse_project(latest)
        report = validate_project(project, workspace_root=ws_path)
        return _ok({
            "project_file": str(latest),
            "summary": report.summary,
            "issue_count": len(report.items),
            "issues": [
                {
                    "severity": str(item.severity),
                    "category": item.category,
                    "message": item.message,
                    "location": item.location,
                }
                for item in report.items
            ],
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def project_summary(workspace_path: str) -> dict:
    """Return a summary of the workspace project including all artifacts.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Project metadata with counts of transcripts, markers, timelines, renders.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        from workshop_video_brain.workspace.manifest import read_manifest

        ws = Path(workspace_path)
        if not ws.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        manifest = read_manifest(ws)

        transcripts = list((ws / "transcripts").glob("*_transcript.json")) if (ws / "transcripts").exists() else []
        markers = list((ws / "markers").glob("*_markers.json")) if (ws / "markers").exists() else []
        timelines = list((ws / "projects" / "working_copies").glob("*.kdenlive")) if (ws / "projects" / "working_copies").exists() else []
        renders = list((ws / "renders").rglob("*.mp4")) if (ws / "renders").exists() else []

        return _ok({
            "workspace_id": str(manifest.workspace_id),
            "title": manifest.project_title,
            "slug": manifest.slug,
            "status": manifest.status,
            "media_root": manifest.media_root,
            "transcript_count": len(transcripts),
            "marker_file_count": len(markers),
            "timeline_count": len(timelines),
            "render_count": len(renders),
            "latest_timeline": str(timelines[-1]) if timelines else None,
        })
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Snapshot tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def snapshot_list(workspace_path: str) -> dict:
    """List all snapshots in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of snapshot records with IDs, timestamps, and descriptions.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.workspace.snapshot import list_snapshots

        records = list_snapshots(workspace_path)
        snaps_dir = ws_path / "projects" / "snapshots"
        snap_dirs = sorted(snaps_dir.iterdir()) if snaps_dir.exists() else []
        dir_names = [d.name for d in snap_dirs if d.is_dir()]

        return _ok({
            "snapshots": [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat(),
                    "project_file_path": r.project_file_path,
                    "description": r.description,
                }
                for r in records
            ],
            "snapshot_dirs": dir_names,
            "count": len(records),
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def snapshot_restore(workspace_path: str, snapshot_id: str) -> dict:
    """Restore a snapshot by its directory name (timestamp-slug).

    Args:
        workspace_path: Path to the workspace root directory.
        snapshot_id: Snapshot directory name, e.g. "20240101_120000-project-v1".

    Returns:
        Confirmation of the restore with the original file path.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        if not snapshot_id or not snapshot_id.strip():
            return invalid_input("snapshot_id must be a non-empty string", "Pass a snapshot id (run snapshot_list to see available snapshots).", param="snapshot_id")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        # Validate that snapshot_id exists
        snap_dir = ws_path / "projects" / "snapshots" / snapshot_id
        if not snap_dir.exists():
            return err(
                f"Snapshot '{snapshot_id}' not found in {workspace_path}/projects/snapshots/",
                error_type="not_found",
                suggestion="Run snapshot_list to see valid snapshot ids for this workspace.",
                given=snapshot_id,
            )
        from workshop_video_brain.workspace.snapshot import restore, list_snapshots

        restore(workspace_path, snapshot_id)
        return _ok({
            "snapshot_id": snapshot_id,
            "restored": True,
            "workspace_path": workspace_path,
        })
    except FileNotFoundError as exc:
        return from_exception(exc)
    except ValueError as exc:
        return from_exception(exc)
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# ForgeFrame init tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def forgeframe_init(
    vault_path: str,
    projects_root: str,
    media_library: str = "",
) -> dict:
    """Initialize ForgeFrame environment with vault structure, media folders, and config.

    Args:
        vault_path: Path to the Obsidian vault root (created if missing).
        projects_root: Root folder for project workspaces.
        media_library: Optional separate media library path.
            Defaults to ``projects_root/Media Library``.

    Returns:
        Structured result with created paths and counts.
    """
    try:
        from pathlib import Path as _Path
        from workshop_video_brain.app.init_system import initialize_forgeframe

        if not vault_path or not vault_path.strip():
            return _err("vault_path must be a non-empty string")
        if not projects_root or not projects_root.strip():
            return _err("projects_root must be a non-empty string")

        media_lib = _Path(media_library) if media_library and media_library.strip() else None
        result = initialize_forgeframe(
            vault_path=vault_path,
            projects_root=projects_root,
            media_library_root=media_lib,
        )
        return _ok({
            "vault_path": result.vault_path,
            "projects_root": result.projects_root,
            "vault_folders_created": result.vault_folders_created,
            "media_folders_created": result.media_folders_created,
            "config_file_written": result.config_file_written,
            "env_file_written": result.env_file_written,
            "notes": result.notes,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def forgeframe_status() -> dict:
    """Check ForgeFrame initialization status.

    Reports what's configured and what's missing: vault path existence,
    projects root, media library, FFmpeg availability, and Whisper availability.

    Returns:
        Structured status report.
    """
    try:
        from workshop_video_brain.app.init_system import check_status
        return _ok(check_status())
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Project tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def project_new(
    title: str,
    brain_dump: str = "",
    project_type: str = "tutorial",
) -> dict:
    """Create a new video project with workspace, vault note, and production plan.

    If a brain dump is provided, automatically generates outline, script,
    and shot plan. Creates organized folder structure for media intake.

    Args:
        title: Project title (e.g., "Zippered Bikepacking Pouch")
        brain_dump: Optional rough idea/description to kick off planning
        project_type: Type of video: tutorial, review, vlog, build
    """
    try:
        if not title or not title.strip():
            return _err("title must be a non-empty string")
        from workshop_video_brain.edit_mcp.pipelines.new_project import create_new_project
        result = create_new_project(
            title=title,
            brain_dump=brain_dump,
            project_type=project_type,
        )
        return _ok({
            "project_title": result.project_title,
            "project_slug": result.project_slug,
            "workspace_path": result.workspace_path,
            "vault_note_path": result.vault_note_path,
            "media_folders_created": result.media_folders_created,
            "outline_generated": result.outline_generated,
            "script_generated": result.script_generated,
            "shot_plan_generated": result.shot_plan_generated,
            "brain_dump": result.brain_dump,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def project_list() -> dict:
    """List all ForgeFrame projects with their status.

    Scans the configured projects root for workspace.yaml files and returns
    project names, statuses, and paths.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.new_project import list_projects
        projects = list_projects()
        return _ok({"projects": projects, "count": len(projects)})
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def project_archive(
    workspace_path: str,
    output_dir: str,
    include_renders: bool = True,
    include_raw: bool = False,
    format: str = "tar.gz",
) -> dict:
    """Archive the workspace into a tar.gz or zip file."""
    from workshop_video_brain.edit_mcp.pipelines.archive import create_archive
    try:
        manifest = create_archive(
            Path(workspace_path),
            Path(output_dir),
            include_renders=include_renders,
            include_raw=include_raw,
            format=format,
        )
        return _ok(manifest.model_dump())
    except Exception as e:
        return from_exception(e)
