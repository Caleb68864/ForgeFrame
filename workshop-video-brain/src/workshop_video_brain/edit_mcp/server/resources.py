"""MCP resource registrations for workshop-video-brain.

Resources provide read access to workspace state as formatted text.
This module must be imported by server.py so the @mcp.resource() decorators
execute and register each resource with the FastMCP instance.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _workspace_summary_text(workspace_path: str) -> str:
    """Return a formatted summary of the workspace manifest."""
    ws = Path(workspace_path)
    manifest_path = ws / "workspace.yaml"
    if not manifest_path.exists():
        return f"No workspace.yaml found at {workspace_path}"
    try:
        from workshop_video_brain.workspace.manifest import read_manifest
        m = read_manifest(ws)
        lines = [
            f"# Workspace: {m.project_title}",
            "",
            f"- **ID**: {m.workspace_id}",
            f"- **Slug**: {m.slug}",
            f"- **Status**: {m.status}",
            f"- **Media Root**: {m.media_root}",
            f"- **Vault Note**: {m.vault_note_path or '(none)'}",
            f"- **Created**: {m.created_at.isoformat()}",
            f"- **Updated**: {m.updated_at.isoformat()}",
        ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading workspace: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://current/summary
# ---------------------------------------------------------------------------

@mcp.resource("workspace://current/summary")
def workspace_current_summary() -> str:
    """Current workspace manifest as formatted markdown text.

    Returns a summary of the workspace identified by WVB_WORKSPACE_ROOT or
    the current working directory.
    """
    import os
    workspace_path = os.environ.get("WVB_WORKSPACE_ROOT", str(Path.cwd()))
    return _workspace_summary_text(workspace_path)


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/media-catalog
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/media-catalog")
def workspace_media_catalog(id: str) -> str:
    """Media asset catalog for a workspace.

    Returns a formatted list of media files found in media/raw/.

    Args:
        id: Workspace path or slug identifier.
    """
    try:
        raw_dir = Path(id) / "media" / "raw"
        if not raw_dir.exists():
            return f"No media/raw directory found at {id}"

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        assets = scan_directory(raw_dir)

        lines = [f"# Media Catalog: {id}", "", f"Total assets: {len(assets)}", ""]
        for a in assets:
            lines.append(f"## {Path(a.path).name}")
            lines.append(f"- **Path**: {a.path}")
            lines.append(f"- **Type**: {a.media_type}")
            if a.duration_seconds:
                lines.append(f"- **Duration**: {a.duration_seconds:.1f}s")
            if a.file_size_bytes:
                mb = a.file_size_bytes / (1024 * 1024)
                lines.append(f"- **Size**: {mb:.1f} MB")
            lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading media catalog: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/transcript-index
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/transcript-index")
def workspace_transcript_index(id: str) -> str:
    """Transcript index for a workspace.

    Returns summaries of all transcripts found in transcripts/.

    Args:
        id: Workspace path.
    """
    try:
        transcripts_dir = Path(id) / "transcripts"
        if not transcripts_dir.exists():
            return f"No transcripts/ directory at {id}"

        from workshop_video_brain.core.models.transcript import Transcript

        json_files = sorted(transcripts_dir.glob("*_transcript.json"))
        if not json_files:
            return "No transcripts found."

        lines = [f"# Transcript Index: {id}", "", f"Total transcripts: {len(json_files)}", ""]
        for jf in json_files:
            try:
                transcript = Transcript.from_json(jf.read_text(encoding="utf-8"))
                word_count = len(transcript.raw_text.split())
                duration = (
                    transcript.segments[-1].end_seconds
                    if transcript.segments
                    else 0.0
                )
                lines.append(f"## {jf.stem}")
                lines.append(f"- **Engine**: {transcript.engine}")
                lines.append(f"- **Language**: {transcript.language}")
                lines.append(f"- **Segments**: {len(transcript.segments)}")
                lines.append(f"- **Words**: ~{word_count}")
                lines.append(f"- **Duration**: {duration:.1f}s")
                if transcript.raw_text:
                    preview = transcript.raw_text[:200].strip()
                    lines.append(f"- **Preview**: {preview}...")
                lines.append("")
            except Exception as exc:
                lines.append(f"## {jf.stem}")
                lines.append(f"- Error: {exc}")
                lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading transcripts: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/markers
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/markers")
def workspace_markers(id: str) -> str:
    """Marker report for a workspace.

    Returns all markers from markers/*.json in a formatted table.

    Args:
        id: Workspace path.
    """
    try:
        markers_dir = Path(id) / "markers"
        if not markers_dir.exists():
            return f"No markers/ directory at {id}"

        marker_files = sorted(markers_dir.glob("*_markers.json"))
        if not marker_files:
            return "No marker files found. Run markers_auto_generate first."

        lines = [f"# Marker Report: {id}", ""]
        total = 0
        for mf in marker_files:
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                lines.append(f"## {mf.stem} ({len(data)} markers)")
                lines.append("")
                lines.append("| Time | Category | Confidence | Reason |")
                lines.append("| --- | --- | --- | --- |")
                for m in data:
                    start = m.get("start_seconds", 0)
                    end = m.get("end_seconds", 0)
                    cat = m.get("category", "")
                    conf = m.get("confidence_score", 0)
                    reason = (m.get("reason", "") or "")[:60].replace("|", "\\|")
                    lines.append(f"| {start:.1f}s–{end:.1f}s | {cat} | {conf:.2f} | {reason} |")
                total += len(data)
                lines.append("")
            except Exception as exc:
                lines.append(f"## {mf.stem} — Error: {exc}")
                lines.append("")

        lines.insert(2, f"Total markers: {total}")
        lines.insert(3, "")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading markers: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/timeline-summary
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/timeline-summary")
def workspace_timeline_summary(id: str) -> str:
    """Timeline summary for a workspace.

    Lists all .kdenlive working copy files with their creation times.

    Args:
        id: Workspace path.
    """
    try:
        working_copies = Path(id) / "projects" / "working_copies"
        if not working_copies.exists():
            return f"No projects/working_copies/ directory at {id}"

        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return "No timeline files found. Run timeline_build_review first."

        lines = [f"# Timeline Summary: {id}", "", f"Total timelines: {len(kdenlive_files)}", ""]
        for kf in kdenlive_files:
            from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
            try:
                project = parse_project(kf)
                lines.append(f"## {kf.name}")
                lines.append(f"- **Title**: {project.title}")
                lines.append(f"- **Producers**: {len(project.producers)}")
                lines.append(f"- **Guides**: {len(project.guides)}")
                lines.append(f"- **Profile**: {project.profile.width}x{project.profile.height} @ {project.profile.fps}fps")
                lines.append("")
            except Exception as exc:
                lines.append(f"## {kf.name} — Error: {exc}")
                lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading timeline summary: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/validation
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/validation")
def workspace_validation(id: str) -> str:
    """Validation report for the latest working copy in a workspace.

    Args:
        id: Workspace path.
    """
    try:
        working_copies = Path(id) / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
        if not kdenlive_files:
            return f"No .kdenlive files found at {id}/projects/working_copies/"

        latest = kdenlive_files[-1]
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

        project = parse_project(latest)
        report = validate_project(project, workspace_root=Path(id))

        lines = [
            f"# Validation Report: {id}",
            "",
            f"**File**: {latest.name}",
            f"**Summary**: {report.summary}",
            "",
        ]
        if report.items:
            lines.append("## Issues")
            lines.append("")
            lines.append("| Severity | Category | Message | Location |")
            lines.append("| --- | --- | --- | --- |")
            for item in report.items:
                msg = item.message.replace("|", "\\|")
                lines.append(f"| {item.severity} | {item.category} | {msg} | {item.location} |")
        else:
            lines.append("No issues found.")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error running validation: {exc}"


# ---------------------------------------------------------------------------
# Resource: workspace://{id}/render-logs
# ---------------------------------------------------------------------------

@mcp.resource("workspace://{id}/render-logs")
def workspace_render_logs(id: str) -> str:
    """Render job status and logs for a workspace.

    Args:
        id: Workspace path.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders
        jobs = list_renders(id)

        if not jobs:
            return f"No render jobs found for workspace: {id}"

        lines = [f"# Render Logs: {id}", "", f"Total jobs: {len(jobs)}", ""]
        for job in jobs:
            lines.append(f"## Job {str(job.id)[:8]}")
            lines.append(f"- **Status**: {job.status}")
            lines.append(f"- **Profile**: {job.profile}")
            lines.append(f"- **Output**: {job.output_path}")
            lines.append(f"- **Started**: {job.started_at.isoformat() if job.started_at else 'not started'}")
            lines.append(f"- **Completed**: {job.completed_at.isoformat() if job.completed_at else 'not completed'}")
            if job.log_path and Path(job.log_path).exists():
                try:
                    log_tail = Path(job.log_path).read_text(encoding="utf-8")[-500:]
                    lines.append(f"- **Log tail**: ```\n{log_tail}\n```")
                except Exception:
                    pass
            lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error reading render logs: {exc}"


# ---------------------------------------------------------------------------
# Resource: system://capabilities
# ---------------------------------------------------------------------------

@mcp.resource("system://capabilities")
def system_capabilities() -> str:
    """Available tools and adapter status for workshop-video-brain.

    Returns a formatted listing of available MCP tools and the status of
    external tool dependencies (FFmpeg, faster-whisper).
    """
    import shutil

    lines = [
        "# System Capabilities",
        "",
        "## External Tool Status",
        "",
    ]

    ffmpeg_ok = shutil.which("ffmpeg") is not None
    melt_ok = shutil.which("melt") is not None
    lines.append(f"- **FFmpeg**: {'available' if ffmpeg_ok else 'NOT FOUND'}")
    lines.append(f"- **melt (MLT)**: {'available' if melt_ok else 'NOT FOUND'}")

    try:
        import faster_whisper  # noqa: F401
        whisper_ok = True
    except ImportError:
        whisper_ok = False
    lines.append(f"- **faster-whisper**: {'available' if whisper_ok else 'NOT INSTALLED'}")
    lines.append("")

    lines.extend([
        "## Available MCP Tools",
        "",
        "### Workspace",
        "- `workspace_create` — create a new workspace",
        "- `workspace_status` — show workspace manifest",
        "",
        "### Media",
        "- `media_ingest` — scan, proxy, transcribe all media",
        "- `media_list_assets` — list assets in media/raw/",
        "- `proxy_generate` — generate proxy files",
        "",
        "### Transcripts",
        "- `transcript_generate` — run transcription pipeline",
        "- `transcript_export` — export transcripts (srt/json/txt)",
        "",
        "### Markers",
        "- `markers_auto_generate` — auto-generate markers from transcripts",
        "- `markers_list` — list marker files and counts",
        "",
        "### Timelines",
        "- `timeline_build_review` — build ranked/chronological review timeline",
        "- `timeline_build_selects` — build selects timeline",
        "",
        "### Project",
        "- `project_create_working_copy` — create initial .kdenlive project",
        "- `project_validate` — validate working copy",
        "- `project_summary` — project metadata summary",
        "- `transitions_apply` — apply transitions to latest working copy",
        "",
        "### Subtitles",
        "- `subtitles_generate` — generate SRT from transcripts",
        "- `subtitles_export` — list exported SRT files",
        "",
        "### Render",
        "- `render_preview` — render with preview profile",
        "- `render_status` — list render jobs",
        "",
        "### Snapshots",
        "- `snapshot_list` — list workspace snapshots",
        "- `snapshot_restore` — restore a snapshot",
        "",
        "## MCP Resources",
        "",
        "- `workspace://current/summary` — current workspace manifest",
        "- `workspace://{id}/media-catalog` — media asset catalog",
        "- `workspace://{id}/transcript-index` — transcript summaries",
        "- `workspace://{id}/markers` — marker report",
        "- `workspace://{id}/timeline-summary` — timeline file list",
        "- `workspace://{id}/validation` — validation report",
        "- `workspace://{id}/render-logs` — render job status",
        "- `system://capabilities` — this document",
    ])
    return "\n".join(lines)
